"""Conservar contexto de incidentes y enlazar los eventos exactos del buzón.

Revision ID: 20261020_0017
Revises: 20261020_0016
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261020_0017"
down_revision: str | Sequence[str] | None = "20261020_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Conserva el contexto disponible y corrige enlaces sin alterar lecturas."""
    op.add_column(
        "notificacion", sa.Column("emergencia_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "notificacion", sa.Column("tarea_bonita_nombre", sa.String(160), nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_notificacion_emergencia_id_emergencia"),
        "notificacion",
        "emergencia",
        ["emergencia_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        sa.text("""
        UPDATE notificacion AS n
        SET emergencia_id = e.id,
            tarea_bonita_nombre = left(substring(n.mensaje FROM
                '^La tarea (.*) de la emergencia #[0-9]+ está fallida'), 160)
        FROM emergencia AS e
        WHERE n.tipo = 'TAREA_BONITA_FALLIDA'
          AND e.id::text = substring(n.mensaje FROM
                'de la emergencia #([0-9]+) está fallida')
    """)
    )
    op.execute(
        sa.text("""
        UPDATE notificacion AS n
        SET ruta = '/notificaciones/' || n.id
        FROM usuario AS u
        WHERE n.usuario_id = u.id AND (
            (u.rol = 'REPRESENTANTE_ONG'
             AND n.tipo IN ('CONVOCATORIA_PUBLICADA', 'CONVOCATORIA_CERRADA')
             AND n.clave_evento ~ ('^convocatoria' || ':' || '[1-9][0-9]*' || ':' || '(publicada|cerrada)$'))
            OR (u.rol = 'COORDINADOR_REGIONAL'
                AND n.tipo = 'OFERTA_RECIBIDA'
                AND n.clave_evento ~ ('^oferta' || ':' || '[1-9][0-9]*' || ':' || 'recibida$'))
            OR (u.rol = 'AUDITOR_DIRECTIVO'
                AND n.tipo = 'TAREA_BONITA_FALLIDA'
                AND n.clave_evento ~ ('^bonita' || ':' || 'tarea' || ':' || '[1-9][0-9]*' || ':' || 'fallida$'))
        )
    """)
    )


def downgrade() -> None:
    """Restaura los destinos anteriores y retira únicamente el nuevo contexto."""
    op.execute(
        sa.text("""
        UPDATE notificacion SET ruta = CASE
            WHEN tipo = 'CONVOCATORIA_PUBLICADA' THEN '/convocatorias'
            WHEN tipo = 'CONVOCATORIA_CERRADA' THEN '/mis-ofertas'
            ELSE '/'
        END
        WHERE ruta = '/notificaciones/' || id
          AND tipo IN ('CONVOCATORIA_PUBLICADA', 'CONVOCATORIA_CERRADA',
                       'OFERTA_RECIBIDA', 'TAREA_BONITA_FALLIDA')
    """)
    )
    op.drop_constraint(
        op.f("fk_notificacion_emergencia_id_emergencia"),
        "notificacion",
        type_="foreignkey",
    )
    op.drop_column("notificacion", "tarea_bonita_nombre")
    op.drop_column("notificacion", "emergencia_id")
