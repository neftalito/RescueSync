"""Agregar claim para serializar la sincronización de convocatorias con Bonita.

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
    """Persiste la propiedad temporal de cada intento contra Bonita."""

    op.add_column(
        "convocatoria",
        sa.Column("bonita_generar_lotes_intento_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "convocatoria",
        sa.Column(
            "bonita_generar_lotes_intento_expira_en",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_convocatoria_bonita_generar_lotes_intento_completo",
        "convocatoria",
        "(bonita_generar_lotes_intento_id IS NULL) = "
        "(bonita_generar_lotes_intento_expira_en IS NULL)",
    )


def downgrade() -> None:
    """Retira el claim de sincronización de convocatorias."""

    op.drop_constraint(
        "ck_convocatoria_bonita_generar_lotes_intento_completo",
        "convocatoria",
        type_="check",
    )
    op.drop_column("convocatoria", "bonita_generar_lotes_intento_expira_en")
    op.drop_column("convocatoria", "bonita_generar_lotes_intento_id")
