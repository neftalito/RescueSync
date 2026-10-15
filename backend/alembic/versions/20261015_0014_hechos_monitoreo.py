"""Conservar hechos confirmados para indicadores de resultado."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261015_0014"
down_revision = "20261015_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hecho_monitoreo",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "emergencia_id",
            sa.BigInteger(),
            sa.ForeignKey("emergencia.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("clave", sa.String(120), nullable=False),
        sa.Column("referencia", sa.String(255), nullable=False),
        sa.Column("datos", postgresql.JSONB(), nullable=False),
        sa.Column(
            "registrado_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("emergencia_id", "clave", name="uq_hecho_emergencia_clave"),
        sa.UniqueConstraint("emergencia_id", "referencia", name="uq_hecho_referencia"),
    )
    op.create_index(
        "ix_hecho_monitoreo_emergencia_id", "hecho_monitoreo", ["emergencia_id"]
    )


def downgrade() -> None:
    op.drop_table("hecho_monitoreo")
