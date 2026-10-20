"""Agregar alertas de tareas fallidas de Bonita al buzón de auditoría."""

from alembic import op

revision = "20261015_0013"
down_revision = "20261015_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Amplía el enum sin reescribir notificaciones existentes."""
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE tipo_notificacion ADD VALUE IF NOT EXISTS 'TAREA_BONITA_FALLIDA'"
        )


def downgrade() -> None:
    """Conserva las alertas como novedades de emergencia al retirar el nuevo tipo."""
    op.execute(
        "UPDATE notificacion SET tipo = 'EMERGENCIA_ESTADO_ACTUALIZADO' WHERE tipo::text = 'TAREA_BONITA_FALLIDA'"
    )
    op.execute("ALTER TYPE tipo_notificacion RENAME TO tipo_notificacion_con_alertas")
    op.execute(
        "CREATE TYPE tipo_notificacion AS ENUM ('EMERGENCIA_REGISTRADA', 'EMERGENCIA_ESTADO_ACTUALIZADO', 'CONVOCATORIA_PUBLICADA', 'CONVOCATORIA_ACTUALIZADA', 'CONVOCATORIA_CERRADA', 'OFERTA_RECIBIDA')"
    )
    op.execute(
        "ALTER TABLE notificacion ALTER COLUMN tipo TYPE tipo_notificacion USING tipo::text::tipo_notificacion"
    )
    op.execute("DROP TYPE tipo_notificacion_con_alertas")
