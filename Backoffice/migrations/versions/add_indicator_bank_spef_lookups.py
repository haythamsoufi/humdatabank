"""Central SP/EF (SPEF) code catalog and optional area_label on indicator_bank.

Revision ID: add_indicator_bank_spef_lookups
Revises: add_running_aireasoningtracestatus
Create Date: 2026-06-12

"""
from __future__ import annotations

import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "add_indicator_bank_spef_lookups"
down_revision = "add_running_aireasoningtracestatus"
branch_labels = None
depends_on = None


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def upgrade():
    op.create_table(
        "indicator_bank_spef",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_translations", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_indicator_bank_spef_code"),
    )
    op.create_index("ix_indicator_bank_spef_code", "indicator_bank_spef", ["code"], unique=False)

    op.add_column(
        "indicator_bank",
        sa.Column("indicator_spef_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "indicator_bank",
        sa.Column("area_label", sa.Text(), nullable=True),
    )
    op.add_column(
        "indicator_bank_history",
        sa.Column("area_label", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_indicator_bank_indicator_spef",
        "indicator_bank",
        "indicator_bank_spef",
        ["indicator_spef_id"],
        ["id"],
    )
    op.create_index("ix_indicator_bank_spef_fk", "indicator_bank", ["indicator_spef_id"])

    now = _now()
    bind = op.get_bind()

    distinct_areas = bind.execute(
        text(
            "SELECT DISTINCT trim(area) AS code FROM indicator_bank "
            "WHERE area IS NOT NULL AND trim(area) <> ''"
        )
    ).fetchall()

    spef_by_code: dict[str, int] = {}
    sort_order = 0
    for (raw_code,) in distinct_areas:
        code = (raw_code or "").strip().upper()
        if not code or code in spef_by_code:
            continue
        sort_order += 10
        bind.execute(
            text(
                "INSERT INTO indicator_bank_spef (code, name, name_translations, sort_order, is_active, created_at, updated_at) "
                "VALUES (:code, :name, NULL, :so, true, :ca, :ua)"
            ),
            {"code": code, "name": code, "so": sort_order, "ca": now, "ua": now},
        )
        row = bind.execute(
            text("SELECT id FROM indicator_bank_spef WHERE upper(code) = :c"),
            {"c": code},
        ).fetchone()
        if row:
            spef_by_code[code] = row[0]

    bank_rows = bind.execute(
        text("SELECT id, area FROM indicator_bank WHERE area IS NOT NULL AND trim(area) <> ''")
    ).fetchall()
    for bid, area_val in bank_rows:
        code = (area_val or "").strip().upper()
        sid = spef_by_code.get(code)
        if not sid:
            continue
        area_label = bind.execute(
            text("SELECT name FROM indicator_bank_spef WHERE id = :sid"),
            {"sid": sid},
        ).scalar()
        bind.execute(
            text(
                "UPDATE indicator_bank SET indicator_spef_id = :sid, area = :code, "
                "area_label = :area_label WHERE id = :bid"
            ),
            {"sid": sid, "code": code, "area_label": area_label, "bid": bid},
        )

    history_rows = bind.execute(
        text(
            "SELECT id, area FROM indicator_bank_history "
            "WHERE area IS NOT NULL AND trim(area) <> ''"
        )
    ).fetchall()
    for hid, area_val in history_rows:
        code = (area_val or "").strip().upper()
        sid = spef_by_code.get(code)
        if not sid:
            continue
        area_label = bind.execute(
            text("SELECT name FROM indicator_bank_spef WHERE id = :sid"),
            {"sid": sid},
        ).scalar()
        bind.execute(
            text("UPDATE indicator_bank_history SET area_label = :area_label WHERE id = :hid"),
            {"area_label": area_label, "hid": hid},
        )


def downgrade():
    op.drop_index("ix_indicator_bank_spef_fk", table_name="indicator_bank")
    op.drop_constraint("fk_indicator_bank_indicator_spef", "indicator_bank", type_="foreignkey")
    op.drop_column("indicator_bank_history", "area_label")
    op.drop_column("indicator_bank", "area_label")
    op.drop_column("indicator_bank", "indicator_spef_id")
    op.drop_index("ix_indicator_bank_spef_code", table_name="indicator_bank_spef")
    op.drop_table("indicator_bank_spef")
