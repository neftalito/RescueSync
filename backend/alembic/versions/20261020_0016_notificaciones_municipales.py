"""Identificar la emergencia y enlazar la ejecución en avisos municipales.

Revision ID: 20261020_0016
Revises: 20261016_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261020_0016"
down_revision: str | Sequence[str] | None = "20261016_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Actualiza los avisos del municipio dueño sin alterar lecturas ni fechas."""
    op.execute(
        sa.text(
            """
            UPDATE notificacion AS n
            SET mensaje = CASE
                    WHEN n.clave_evento = 'convocatoria:' || c.id || ':' || 'publicada'
                    THEN 'El centro coordinador publicó la convocatoria de la emergencia en '
                         || e.zona || ': ' || e.descripcion
                    ELSE 'Cerró la convocatoria y las ofertas están siendo evaluadas. '
                         || 'Emergencia en ' || e.zona || ': ' || e.descripcion
                END,
                ruta = '/emergencias/' || e.id || '/ejecucion'
            FROM convocatoria AS c
            JOIN emergencia AS e ON e.id = c.emergencia_id
            JOIN usuario AS u ON u.organizacion_id = e.municipio_id
            WHERE n.usuario_id = u.id
              AND u.rol = 'OPERADOR_MUNICIPAL'
              AND n.tipo = 'EMERGENCIA_ESTADO_ACTUALIZADO'
              AND n.clave_evento IN (
                  'convocatoria:' || c.id || ':' || 'publicada',
                  'convocatoria:' || c.id || ':' || 'cerrada'
              )
            """
        )
    )


def downgrade() -> None:
    """Restaura los textos anteriores sin eliminar avisos ni su estado de lectura."""
    op.execute(
        sa.text(
            """
            UPDATE notificacion AS n
            SET mensaje = CASE
                    WHEN n.clave_evento = 'convocatoria:' || c.id || ':' || 'publicada'
                    THEN 'El centro coordinador publicó la convocatoria de la emergencia.'
                    ELSE 'Cerró la convocatoria y las ofertas están siendo evaluadas.'
                END,
                ruta = '/'
            FROM convocatoria AS c
            JOIN emergencia AS e ON e.id = c.emergencia_id
            JOIN usuario AS u ON u.organizacion_id = e.municipio_id
            WHERE n.usuario_id = u.id
              AND u.rol = 'OPERADOR_MUNICIPAL'
              AND n.tipo = 'EMERGENCIA_ESTADO_ACTUALIZADO'
              AND n.ruta = '/emergencias/' || e.id || '/ejecucion'
              AND n.clave_evento IN (
                  'convocatoria:' || c.id || ':' || 'publicada',
                  'convocatoria:' || c.id || ':' || 'cerrada'
              )
            """
        )
    )
