"""Guardar la prioridad calculada para las nuevas emergencias.

Revision ID: 20261119_0018
Revises: 20261020_0017
"""

import sqlalchemy as sa

from alembic import op

revision = "20261119_0018"
down_revision = "20261020_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Permite conservar emergencias históricas con prioridad desconocida."""

    op.add_column("emergencia", sa.Column("prioridad", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_emergencia_prioridad_rango"),
        "emergencia",
        "prioridad BETWEEN 1 AND 10",
    )


def downgrade() -> None:
    """Retira la restricción y la columna de prioridad."""

    op.drop_constraint(
        op.f("ck_emergencia_prioridad_rango"), "emergencia", type_="check"
    )
    op.drop_column("emergencia", "prioridad")
