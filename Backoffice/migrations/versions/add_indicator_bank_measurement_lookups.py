"""Central indicator measurement types and units + FKs on bank and form items.

Revision ID: add_indicator_bank_measurement_lookups
Revises: indicator_bank_type_unit_translations
Create Date: 2026-04-22

"""
from __future__ import annotations

import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "add_indicator_bank_measurement_lookups"
down_revision = "indicator_bank_type_unit_translations"
branch_labels = None
depends_on = None


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def upgrade():
    op.create_table(
        "indicator_bank_type",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_translations", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_indicator_bank_type_code"),
    )
    op.create_index("ix_indicator_bank_type_code", "indicator_bank_type", ["code"], unique=False)

    op.create_table(
        "indicator_bank_unit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_translations", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "allows_disaggregation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_indicator_bank_unit_code"),
    )
    op.create_index("ix_indicator_bank_unit_code", "indicator_bank_unit", ["code"], unique=False)

    now = _now()
    bind = op.get_bind()

    type_rows = [
        ("number", "Number", 10),
        ("percentage", "Percentage", 20),
        ("text", "Text", 30),
        ("yesno", "Yes/No", 40),
        ("date", "Date", 50),
        ("boolean", "Boolean", 60),
        ("integer", "Integer", 70),
    ]
    for code, name, so in type_rows:
        bind.execute(
            text(
                "INSERT INTO indicator_bank_type (code, name, name_translations, sort_order, is_active, created_at, updated_at) "
                "VALUES (:code, :name, NULL, :so, true, :ca, :ua)"
            ),
            {"code": code, "name": name, "so": so, "ca": now, "ua": now},
        )

    # (code, name, sort_order, allows_disaggregation)
    unit_rows = [
        ("people", "People", 10, 1),
        ("volunteers", "Volunteers", 20, 1),
        ("staff", "Staff", 30, 1),
        ("units", "Units", 100, 0),
        ("percent", "Percent", 110, 0),
        ("usd", "USD", 120, 0),
        ("eur", "EUR", 130, 0),
        ("items", "Items", 140, 0),
        ("sessions", "Sessions", 150, 0),
        ("trainings", "Trainings", 160, 0),
        ("beneficiaries", "Beneficiaries", 170, 0),
        ("households", "Households", 180, 0),
        ("communities", "Communities", 190, 0),
        ("organizations", "Organizations", 200, 0),
        ("facilities", "Facilities", 210, 0),
        ("centers", "Centers", 220, 0),
        ("clinics", "Clinics", 230, 0),
        ("hospitals", "Hospitals", 240, 0),
        ("schools", "Schools", 250, 0),
        ("students", "Students", 260, 0),
        ("teachers", "Teachers", 270, 0),
        ("professionals", "Professionals", 280, 0),
        ("specialists", "Specialists", 290, 0),
        ("experts", "Experts", 300, 0),
        ("instructors", "Instructors", 310, 0),
        ("participants", "Participants", 320, 0),
        ("recipients", "Recipients", 330, 0),
        ("victims", "Victims", 340, 0),
        ("survivors", "Survivors", 350, 0),
        ("refugees", "Refugees", 360, 0),
        ("migrants", "Migrants", 370, 0),
        ("displaced", "Displaced", 380, 0),
    ]
    for code, name, so, ad in unit_rows:
        bind.execute(
            text(
                "INSERT INTO indicator_bank_unit (code, name, name_translations, sort_order, is_active, allows_disaggregation, created_at, updated_at) "
                "VALUES (:code, :name, NULL, :so, true, :ad, :ca, :ua)"
            ),
            {"code": code, "name": name, "so": so, "ad": bool(ad), "ca": now, "ua": now},
        )

    op.add_column(
        "indicator_bank", sa.Column("indicator_type_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "indicator_bank", sa.Column("indicator_unit_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_indicator_bank_indicator_type",
        "indicator_bank",
        "indicator_bank_type",
        ["indicator_type_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_indicator_bank_indicator_unit",
        "indicator_bank",
        "indicator_bank_unit",
        ["indicator_unit_id"],
        ["id"],
    )
    op.create_index("ix_indicator_bank_type_fk", "indicator_bank", ["indicator_type_id"])
    op.create_index("ix_indicator_bank_unit_fk", "indicator_bank", ["indicator_unit_id"])

    # Backfill: match type/unit strings to lookup rows (case-insensitive)
    bank_rows = bind.execute(
        text("SELECT id, type, unit FROM indicator_bank")
    ).fetchall()
    type_by_code = {
        (r[0] or "").strip().lower(): r[1]
        for r in bind.execute(
            text("SELECT code, id FROM indicator_bank_type")
        ).fetchall()
    }

    for bid, t_str, u_str in bank_rows:
        tid = None
        if t_str and str(t_str).strip():
            k = str(t_str).strip().lower()
            if k in type_by_code:
                tid = type_by_code[k]
            else:
                k2 = k.replace(" ", "")
                for code, tpk in type_by_code.items():
                    if code.replace("_", "") == k2:
                        tid = tpk
                        break
        uid = None
        if u_str and str(u_str).strip():
            urow = bind.execute(
                text("SELECT id FROM indicator_bank_unit WHERE lower(code) = :c"),
                {"c": str(u_str).strip().lower()},
            ).fetchone()
            if urow:
                uid = urow[0]
        if tid or uid:
            bind.execute(
                text(
                    "UPDATE indicator_bank SET indicator_type_id = COALESCE(:tid, indicator_type_id), "
                    "indicator_unit_id = COALESCE(:uid, indicator_unit_id) WHERE id = :bid"
                ),
                {"tid": tid, "uid": uid, "bid": bid},
            )

    # Denormalize type/unit strings to canonical codes
    for bid, t_str, u_str in bank_rows:
        rowt = bind.execute(
            text(
                "SELECT t.code, u.code FROM indicator_bank b "
                "LEFT JOIN indicator_bank_type t ON b.indicator_type_id = t.id "
                "LEFT JOIN indicator_bank_unit u ON b.indicator_unit_id = u.id "
                "WHERE b.id = :id"
            ),
            {"id": bid},
        ).fetchone()
        if not rowt:
            continue
        tcode, ucode = rowt[0], rowt[1]
        if tcode is not None:
            bind.execute(
                text("UPDATE indicator_bank SET type = :t WHERE id = :id"),
                {"t": str(tcode)[:50], "id": bid},
            )
        if ucode is not None:
            bind.execute(
                text("UPDATE indicator_bank SET unit = :u WHERE id = :id"),
                {"u": str(ucode)[:50], "id": bid},
            )
        elif tcode and not ucode:
            bind.execute(
                text("UPDATE indicator_bank SET unit = NULL WHERE id = :id"), {"id": bid}
            )

    op.add_column("form_item", sa.Column("indicator_type_id", sa.Integer(), nullable=True))
    op.add_column("form_item", sa.Column("indicator_unit_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_form_item_indicator_type",
        "form_item",
        "indicator_bank_type",
        ["indicator_type_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_form_item_indicator_unit",
        "form_item",
        "indicator_bank_unit",
        ["indicator_unit_id"],
        ["id"],
    )
    op.create_index("ix_form_item_indicator_type", "form_item", ["indicator_type_id"])
    op.create_index("ix_form_item_indicator_unit", "form_item", ["indicator_unit_id"])

    fi_rows = bind.execute(
        text("SELECT id, type, unit, indicator_bank_id FROM form_item WHERE item_type = 'indicator'")
    ).fetchall()
    for fid, ft, fu, bank_id in fi_rows:
        tid, uid = None, None
        if bank_id:
            brow = bind.execute(
                text(
                    "SELECT indicator_type_id, indicator_unit_id FROM indicator_bank WHERE id = :b"
                ),
                {"b": bank_id},
            ).fetchone()
            if brow:
                tid, uid = brow[0], brow[1]
        if not tid and ft and str(ft).strip():
            tcode = str(ft).strip().lower()
            tr = bind.execute(
                text("SELECT id FROM indicator_bank_type WHERE lower(code) = :c"), {"c": tcode}
            ).fetchone()
            if tr:
                tid = tr[0]
        if not uid and fu and str(fu).strip():
            ur = bind.execute(
                text("SELECT id FROM indicator_bank_unit WHERE lower(code) = :c"),
                {"c": str(fu).strip().lower()},
            ).fetchone()
            if ur:
                uid = ur[0]
        if tid or uid:
            bind.execute(
                text(
                    "UPDATE form_item SET indicator_type_id = COALESCE(:tid, indicator_type_id), "
                    "indicator_unit_id = COALESCE(:uid, indicator_unit_id) WHERE id = :fid"
                ),
                {"tid": tid, "uid": uid, "fid": fid},
            )
        frow2 = bind.execute(
            text(
                "SELECT t.code, u.code FROM form_item fi "
                "LEFT JOIN indicator_bank_type t ON fi.indicator_type_id = t.id "
                "LEFT JOIN indicator_bank_unit u ON fi.indicator_unit_id = u.id "
                "WHERE fi.id = :id"
            ),
            {"id": fid},
        ).fetchone()
        if frow2 and frow2[0] is not None:
            bind.execute(
                text("UPDATE form_item SET type = :t WHERE id = :id"),
                {"t": str(frow2[0])[:50], "id": fid},
            )
        if frow2 and frow2[1] is not None:
            bind.execute(
                text("UPDATE form_item SET unit = :u WHERE id = :id"),
                {"u": str(frow2[1])[:50], "id": fid},
            )
        elif frow2 and frow2[0] and frow2[1] is None:
            bind.execute(text("UPDATE form_item SET unit = NULL WHERE id = :id"), {"id": fid})


def downgrade():
    op.drop_index("ix_form_item_indicator_unit", table_name="form_item")
    op.drop_index("ix_form_item_indicator_type", table_name="form_item")
    op.drop_constraint("fk_form_item_indicator_unit", "form_item", type_="foreignkey")
    op.drop_constraint("fk_form_item_indicator_type", "form_item", type_="foreignkey")
    op.drop_column("form_item", "indicator_unit_id")
    op.drop_column("form_item", "indicator_type_id")

    op.drop_index("ix_indicator_bank_unit_fk", table_name="indicator_bank")
    op.drop_index("ix_indicator_bank_type_fk", table_name="indicator_bank")
    op.drop_constraint("fk_indicator_bank_indicator_unit", "indicator_bank", type_="foreignkey")
    op.drop_constraint("fk_indicator_bank_indicator_type", "indicator_bank", type_="foreignkey")
    op.drop_column("indicator_bank", "indicator_unit_id")
    op.drop_column("indicator_bank", "indicator_type_id")

    op.drop_index("ix_indicator_bank_unit_code", table_name="indicator_bank_unit")
    op.drop_table("indicator_bank_unit")
    op.drop_index("ix_indicator_bank_type_code", table_name="indicator_bank_type")
    op.drop_table("indicator_bank_type")
