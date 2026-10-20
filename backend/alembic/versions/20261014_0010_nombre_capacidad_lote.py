"""Admitir el nombre completo de una capacidad nacional en el lote.

Revision ID: 20261014_0010
Revises: 20261014_0009
"""

import sqlalchemy as sa

from alembic import op

revision: str = "20261014_0010"
down_revision: str | None = "20261014_0009"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column(
        "lote",
        "tipo_necesidad",
        existing_type=sa.String(120),
        type_=sa.String(160),
        existing_nullable=False,
    )


def downgrade() -> None:
    # PostgreSQL rechaza la reducción si hay nombres largos; no se truncan datos.
    op.alter_column(
        "lote",
        "tipo_necesidad",
        existing_type=sa.String(160),
        type_=sa.String(120),
        existing_nullable=False,
    )
