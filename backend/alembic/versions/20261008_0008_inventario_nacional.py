"""Vincular ONGs y conservar conexiones nacionales temporales cifradas.

Revision ID: 20261008_0008
Revises: 20260929_0007
"""

import sqlalchemy as sa

from alembic import op

revision: str = "20261008_0008"
down_revision: str | None = "20260929_0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "organizacion", sa.Column("ong_nacional_id", sa.Uuid(), nullable=True)
    )
    op.create_unique_constraint(
        "uq_organizacion_ong_nacional_id", "organizacion", ["ong_nacional_id"]
    )
    op.create_check_constraint(
        "ck_organizacion_vinculo_nacional_solo_ong",
        "organizacion",
        "ong_nacional_id IS NULL OR tipo = 'ONG'",
    )
    op.create_table(
        "conexion_nacional",
        sa.Column(
            "usuario_id",
            sa.BigInteger(),
            sa.ForeignKey("usuario.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("version_sesion", sa.Integer(), nullable=False),
        sa.Column("ong_id", sa.Uuid(), nullable=False),
        sa.Column("token_cifrado", sa.String(4096), nullable=False),
        sa.Column("expira_en", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "version_sesion > 0", name="ck_conexion_nacional_version_sesion_positiva"
        ),
    )


def downgrade() -> None:
    op.drop_table("conexion_nacional")
    op.drop_constraint(
        "ck_organizacion_vinculo_nacional_solo_ong", "organizacion", type_="check"
    )
    op.drop_constraint(
        "uq_organizacion_ong_nacional_id", "organizacion", type_="unique"
    )
    op.drop_column("organizacion", "ong_nacional_id")
