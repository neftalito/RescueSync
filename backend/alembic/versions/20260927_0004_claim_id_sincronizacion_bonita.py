"""Agregar identificador de reclamo a la sincronización de Bonita.

Revision ID: 20260927_0004
Revises: 20260927_0003
Create Date: 2026-09-27
"""

import sqlalchemy as sa

from alembic import op

revision: str = "20260927_0004"
down_revision: str | None = "20260927_0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Distingue qué intento es dueño del reclamo `EN_PROGRESO` vigente."""

    op.add_column(
        "convocatoria",
        sa.Column("bonita_generar_lotes_claim_id", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    """Retira el identificador de reclamo."""

    op.drop_column("convocatoria", "bonita_generar_lotes_claim_id")
