"""Conservar identidad y secreto de los reintentos de alta nacional."""

import sqlalchemy as sa

from alembic import op

revision = "20261015_0012"
down_revision = "20261015_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aprovisionamiento_nacional",
        sa.Column(
            "organizacion_id",
            sa.BigInteger(),
            sa.ForeignKey("organizacion.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("referencia", sa.Uuid(), nullable=False, unique=True),
        sa.Column("nombre", sa.String(160), nullable=False),
        sa.Column("email_contacto", sa.String(320), nullable=True),
        sa.Column("secreto_cifrado", sa.String(1024), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("aprovisionamiento_nacional")
