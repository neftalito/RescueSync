"""Credenciales institucionales independientes de las sesiones personales."""

import sqlalchemy as sa

from alembic import op

revision = "20261015_0011"
down_revision = "20261014_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "acceso_nacional",
        sa.Column(
            "organizacion_id",
            sa.BigInteger(),
            sa.ForeignKey("organizacion.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("ong_id", sa.Uuid(), nullable=False),
        sa.Column("cuenta_id", sa.Uuid(), nullable=False),
        sa.Column("configuracion_id", sa.Uuid(), nullable=False),
        sa.Column("identificador_login", sa.String(320), nullable=False),
        sa.Column("secreto_cifrado", sa.String(1024), nullable=False),
        sa.Column("token_cifrado", sa.String(4096)),
        sa.Column("expira_en", sa.DateTime(timezone=True)),
        sa.Column(
            "requiere_revision", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    # Los tokens manuales no sirven para obtener nuevas credenciales técnicas.
    op.execute("DELETE FROM conexion_nacional")


def downgrade() -> None:
    op.drop_table("acceso_nacional")
