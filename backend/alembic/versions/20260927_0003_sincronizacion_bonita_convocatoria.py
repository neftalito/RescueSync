"""Agregar sincronización de Bonita a la convocatoria.

Revision ID: 20260927_0003
Revises: 20260917_0002
Create Date: 2026-09-27
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260927_0003"
down_revision: str | None = "20260917_0002"
branch_labels: str | None = None
depends_on: str | None = None

ESTADO_TAREA_BONITA = postgresql.ENUM(
    "PENDIENTE",
    "EN_PROGRESO",
    "COMPLETADA",
    "ERROR",
    "RESULTADO_DESCONOCIDO",
    name="estado_tarea_bonita",
    create_type=False,
)


def upgrade() -> None:
    """Registra el resultado de completar `Generar lotes de necesidades`."""

    bind = op.get_bind()
    ESTADO_TAREA_BONITA.create(bind, checkfirst=True)

    op.add_column(
        "convocatoria",
        sa.Column(
            "bonita_generar_lotes_estado",
            ESTADO_TAREA_BONITA,
            server_default=sa.text("'PENDIENTE'::estado_tarea_bonita"),
            nullable=False,
        ),
    )
    op.add_column(
        "convocatoria",
        sa.Column("bonita_generar_lotes_ultimo_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "convocatoria",
        sa.Column(
            "bonita_generar_lotes_ultimo_intento_en",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Retira la sincronización de Bonita de la convocatoria."""

    op.drop_column("convocatoria", "bonita_generar_lotes_ultimo_intento_en")
    op.drop_column("convocatoria", "bonita_generar_lotes_ultimo_error")
    op.drop_column("convocatoria", "bonita_generar_lotes_estado")

    bind = op.get_bind()
    ESTADO_TAREA_BONITA.drop(bind, checkfirst=True)
