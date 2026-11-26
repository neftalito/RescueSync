"""Guardar las cantidades declaradas por la ONG al finalizar.

Revision ID: 20261126_0019
Revises: 20261119_0018
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20261126_0019"
down_revision = "20261119_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Conserva las finalizaciones anteriores con cantidades desconocidas."""
    op.add_column("finalizacion_ong", sa.Column("ejecucion", JSONB(), nullable=True))


def downgrade() -> None:
    """Retira el registro de cantidades declaradas."""
    op.drop_column("finalizacion_ong", "ejecucion")
