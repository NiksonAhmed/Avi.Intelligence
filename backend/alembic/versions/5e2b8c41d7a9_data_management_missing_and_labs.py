"""Data Management: missing data details and lab result flags

Revision ID: 5e2b8c41d7a9
Revises: 7cd8b74240c2
Create Date: 2026-11-12

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5e2b8c41d7a9"
down_revision: str | Sequence[str] | None = "7cd8b74240c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MISSING_COLUMNS = [
    ("site_name", sa.String(length=300)),
    ("event_name", sa.String(length=200)),
    ("event_date", sa.DateTime(timezone=True)),
    ("form_name", sa.String(length=200)),
    ("item_label", sa.String(length=300)),
    ("saved_at", sa.DateTime(timezone=True)),
]


def upgrade() -> None:
    with op.batch_alter_table("dm_missing_items") as batch:
        for name, kind in _MISSING_COLUMNS:
            batch.add_column(sa.Column(name, kind, nullable=True))
    op.create_table(
        "dm_lab_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False),
        sa.Column("connection", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("study_code", sa.String(length=100), nullable=False),
        sa.Column("site_code", sa.String(length=64), nullable=False),
        sa.Column("site_name", sa.String(length=300), nullable=False),
        sa.Column("subject_id", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=True),
        sa.Column("event_name", sa.String(length=200), nullable=True),
        sa.Column("event_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("form_id", sa.String(length=64), nullable=False),
        sa.Column("form_name", sa.String(length=200), nullable=True),
        sa.Column("analyte", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("out_of_range", sa.String(length=8), nullable=True),
        sa.Column("unit_missing", sa.Boolean(), nullable=False),
        sa.Column("range_missing", sa.Boolean(), nullable=False),
        sa.Column("evaluation", sa.String(length=16), nullable=True),
        sa.Column("cs_reference_missing", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("tenant_id", "connection", "subject_id"):
        op.create_index(op.f(f"ix_dm_lab_results_{column}"), "dm_lab_results", [column])


def downgrade() -> None:
    for column in ("subject_id", "connection", "tenant_id"):
        op.drop_index(op.f(f"ix_dm_lab_results_{column}"), table_name="dm_lab_results")
    op.drop_table("dm_lab_results")
    with op.batch_alter_table("dm_missing_items") as batch:
        for name, _kind in reversed(_MISSING_COLUMNS):
            batch.drop_column(name)
