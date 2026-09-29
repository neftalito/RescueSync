"""Agregar notificaciones persistentes por usuario.

Revision ID: 20260928_0006
Revises: 20260928_0005
Create Date: 2026-09-28
"""

import sqlalchemy as sa

from alembic import op

revision: str = "20260928_0006"
down_revision: str | None = "20260928_0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Crea el buzón durable y su enum de eventos operativos."""

    tipo_notificacion = sa.Enum(
        "EMERGENCIA_REGISTRADA",
        "EMERGENCIA_ESTADO_ACTUALIZADO",
        "CONVOCATORIA_PUBLICADA",
        "CONVOCATORIA_ACTUALIZADA",
        "CONVOCATORIA_CERRADA",
        "OFERTA_RECIBIDA",
        name="tipo_notificacion",
    )
    op.create_table(
        "notificacion",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("clave_evento", sa.String(length=180), nullable=False),
        sa.Column("tipo", tipo_notificacion, nullable=False),
        sa.Column("titulo", sa.String(length=140), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column("ruta", sa.String(length=255), nullable=True),
        sa.Column("leida_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(clave_evento) <> ''",
            name=op.f("ck_notificacion_clave_evento_no_vacia"),
        ),
        sa.CheckConstraint(
            "btrim(mensaje) <> ''",
            name=op.f("ck_notificacion_mensaje_no_vacio"),
        ),
        sa.CheckConstraint(
            "ruta IS NULL OR ruta LIKE '/%'",
            name=op.f("ck_notificacion_ruta_relativa"),
        ),
        sa.CheckConstraint(
            "btrim(titulo) <> ''",
            name=op.f("ck_notificacion_titulo_no_vacio"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_notificacion_usuario_id_usuario"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notificacion")),
        sa.UniqueConstraint(
            "usuario_id",
            "clave_evento",
            name="uq_notificacion_usuario_evento",
        ),
    )
    op.create_index(
        "ix_notificacion_usuario_creada",
        "notificacion",
        ["usuario_id", "creada_en"],
        unique=False,
    )
    op.create_index(
        "ix_notificacion_usuario_leida",
        "notificacion",
        ["usuario_id", "leida_en"],
        unique=False,
    )


def downgrade() -> None:
    """Elimina el buzón y el enum sin afectar datos operativos."""

    op.drop_index("ix_notificacion_usuario_leida", table_name="notificacion")
    op.drop_index("ix_notificacion_usuario_creada", table_name="notificacion")
    op.drop_table("notificacion")
    op.execute("DROP TYPE tipo_notificacion")
