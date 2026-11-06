"""knowledge document details

Document control details read from inside each indexed SOP (cover page, change history).

Revision ID: d967c67a8505
Revises: 18a9010a47f4
Create Date: 2026-11-06 17:25:26.768405

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d967c67a8505"
down_revision: str | Sequence[str] | None = "18a9010a47f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.add_column(sa.Column("details", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("knowledge_documents") as batch:
        batch.drop_column("details")
