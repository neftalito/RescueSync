"""Reforzar reclamos Bonita y lotes ofertables.

Revision ID: 20260928_0005
Revises: 20260927_0004
Create Date: 2026-09-28
"""

import sqlalchemy as sa

from alembic import op

revision: str = "20260928_0005"
down_revision: str | None = "20260927_0004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Agrega el reclamo de vinculación y exige lotes publicados al ofertar."""

    op.add_column(
        "emergencia",
        sa.Column("bonita_claim_id", sa.String(length=32), nullable=True),
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validar_oferta_item_convocatoria()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM oferta_version AS version_actual
                JOIN oferta AS oferta_actual
                  ON oferta_actual.id = version_actual.oferta_id
                WHERE version_actual.id = NEW.oferta_version_id
                  AND oferta_actual.convocatoria_id = NEW.convocatoria_id
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'El ítem no pertenece a la convocatoria de su oferta',
                    CONSTRAINT = 'ck_oferta_item_misma_convocatoria';
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM convocatoria_lote AS publicacion
                JOIN lote AS lote_publicado
                  ON lote_publicado.id = publicacion.lote_id
                WHERE publicacion.convocatoria_id = NEW.convocatoria_id
                  AND publicacion.lote_id = NEW.lote_id
                  AND lote_publicado.estado = 'PUBLICADO'
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'El lote no está publicado en la convocatoria',
                    CONSTRAINT = 'ck_oferta_item_lote_publicado';
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        DROP TRIGGER trg_oferta_item_convocatoria ON oferta_item;
        CREATE TRIGGER trg_oferta_item_convocatoria
        BEFORE INSERT OR UPDATE OF oferta_version_id, convocatoria_id, lote_id
        ON oferta_item
        FOR EACH ROW
        EXECUTE FUNCTION validar_oferta_item_convocatoria();
        """
    )


def downgrade() -> None:
    """Restaura la validación anterior y retira el reclamo de vinculación."""

    op.execute(
        """
        DROP TRIGGER trg_oferta_item_convocatoria ON oferta_item;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validar_oferta_item_convocatoria()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM oferta_version AS version_actual
                JOIN oferta AS oferta_actual
                  ON oferta_actual.id = version_actual.oferta_id
                WHERE version_actual.id = NEW.oferta_version_id
                  AND oferta_actual.convocatoria_id = NEW.convocatoria_id
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'El ítem no pertenece a la convocatoria de su oferta',
                    CONSTRAINT = 'ck_oferta_item_misma_convocatoria';
            END IF;

            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_oferta_item_convocatoria
        BEFORE INSERT OR UPDATE OF oferta_version_id, convocatoria_id ON oferta_item
        FOR EACH ROW
        EXECUTE FUNCTION validar_oferta_item_convocatoria();
        """
    )
    op.drop_column("emergencia", "bonita_claim_id")
