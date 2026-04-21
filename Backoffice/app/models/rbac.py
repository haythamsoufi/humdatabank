"""
RBAC models (roles, permissions, scoped grants).

Design goals:
- Multi-role per user (User <-> Role).
- Permission codes are stable strings (e.g., "admin.users.view", "assignment.submit").
- Scoped grants allow exceptions (allow/deny) at different scope levels.
"""

from __future__ import annotations

from app.utils.datetime_helpers import utcnow
from ..extensions import db


class RbacPermission(db.Model):
    __tablename__ = "rbac_permission"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(150), nullable=False, unique=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RbacPermission {self.code}>"


class RbacRole(db.Model):
    __tablename__ = "rbac_role"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(100), nullable=False, unique=True, index=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)

    created_by_user = db.relationship("User", foreign_keys=[created_by_user_id])

    permissions = db.relationship(
        "RbacPermission",
        secondary="rbac_role_permission",
        lazy="select",
        backref=db.backref("roles", lazy="select"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RbacRole {self.code}>"


class RbacRolePermission(db.Model):
    __tablename__ = "rbac_role_permission"

    role_id = db.Column(db.Integer, db.ForeignKey("rbac_role.id", ondelete="CASCADE"), primary_key=True)
    permission_id = db.Column(db.Integer, db.ForeignKey("rbac_permission.id", ondelete="CASCADE"), primary_key=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        db.Index("ix_rbac_role_permission_role", "role_id"),
        db.Index("ix_rbac_role_permission_permission", "permission_id"),
    )


class RbacUserRole(db.Model):
    __tablename__ = "rbac_user_role"

    user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey("rbac_role.id", ondelete="CASCADE"), primary_key=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    __table_args__ = (
        db.Index("ix_rbac_user_role_user", "user_id"),
        db.Index("ix_rbac_user_role_role", "role_id"),
    )


class RbacAccessGrant(db.Model):
    """
    Scoped allow/deny grants.

    principal_type/principal_id allow us to attach grants to either:
    - a specific user (principal_type='user', principal_id=user.id)
    - a role (principal_type='role', principal_id=role.id)
    """

    __tablename__ = "rbac_access_grant"

    id = db.Column(db.Integer, primary_key=True)

    principal_type = db.Column(db.String(20), nullable=False)  # 'user' | 'role'
    principal_id = db.Column(db.Integer, nullable=False)

    permission_id = db.Column(db.Integer, db.ForeignKey("rbac_permission.id", ondelete="CASCADE"), nullable=False)
    permission = db.relationship("RbacPermission", foreign_keys=[permission_id])

    scope_kind = db.Column(db.String(20), nullable=False)  # 'global' | 'entity' | 'template' | 'assignment'

    # Scope payload (nullable depending on scope_kind)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    template_id = db.Column(db.Integer, db.ForeignKey("form_template.id", ondelete="CASCADE"), nullable=True)
    assigned_form_id = db.Column(db.Integer, db.ForeignKey("assigned_form.id", ondelete="CASCADE"), nullable=True)

    effect = db.Column(db.String(10), nullable=False, default="allow")  # 'allow' | 'deny'

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), nullable=True)

    created_by_user = db.relationship("User", foreign_keys=[created_by_user_id])

    __table_args__ = (
        # Basic data integrity
        db.CheckConstraint("principal_type IN ('user','role')", name="ck_rbac_access_grant_principal_type"),
        db.CheckConstraint("scope_kind IN ('global','entity','template','assignment')", name="ck_rbac_access_grant_scope_kind"),
        db.CheckConstraint("effect IN ('allow','deny')", name="ck_rbac_access_grant_effect"),

        # Enforce valid scope payload shape.
        #
        # NOTE: True uniqueness for grants is enforced in PostgreSQL via partial
        # unique indexes per scope_kind (see Alembic migration
        # `fix_rbac_access_grant_integrity.py`). We intentionally do NOT model
        # those partial indexes here to avoid misleading ORM-level constraints
        # (the old "unique across nullable columns" approach is not correct in
        # PostgreSQL).
        db.CheckConstraint(
            """
            (
              (scope_kind = 'global'
                AND entity_type IS NULL AND entity_id IS NULL AND template_id IS NULL AND assigned_form_id IS NULL)
              OR
              (scope_kind = 'entity'
                AND entity_type IS NOT NULL AND entity_type <> '' AND entity_id IS NOT NULL
                AND template_id IS NULL AND assigned_form_id IS NULL)
              OR
              (scope_kind = 'template'
                AND template_id IS NOT NULL
                AND entity_type IS NULL AND entity_id IS NULL AND assigned_form_id IS NULL)
              OR
              (scope_kind = 'assignment'
                AND assigned_form_id IS NOT NULL
                AND entity_type IS NULL AND entity_id IS NULL AND template_id IS NULL)
            )
            """,
            name="ck_rbac_access_grant_scope_payload",
        ),

        # Query performance indexes
        db.Index("ix_rbac_access_grant_principal", "principal_type", "principal_id"),
        db.Index("ix_rbac_access_grant_permission", "permission_id"),
        db.Index("ix_rbac_access_grant_scope_template", "scope_kind", "template_id"),
        db.Index("ix_rbac_access_grant_scope_assignment", "scope_kind", "assigned_form_id"),
        db.Index("ix_rbac_access_grant_scope_entity", "scope_kind", "entity_type", "entity_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RbacAccessGrant {self.effect} {self.principal_type}:{self.principal_id} {getattr(self.permission, 'code', self.permission_id)} {self.scope_kind}>"
