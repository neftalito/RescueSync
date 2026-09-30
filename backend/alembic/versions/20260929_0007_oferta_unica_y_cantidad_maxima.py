"""Exigir una oferta por ONG y limitar cada cantidad al lote.

Revision ID: 20260929_0007
Revises: 20260928_0006
Create Date: 2026-09-29
"""

import sqlalchemy as sa

from alembic import op

revision: str = "20260929_0007"
down_revision: str | None = "20260928_0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Protege la identidad estable y el máximo publicable de cada aporte."""

    op.add_column(
        "oferta",
        sa.Column("fusionada_en_oferta_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_oferta_fusionada_en_oferta_id_oferta",
        "oferta",
        "oferta",
        ["fusionada_en_oferta_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "fusion_distinta",
        "oferta",
        "fusionada_en_oferta_id IS NULL OR fusionada_en_oferta_id <> id",
    )
    op.execute(
        """
        WITH ofertas_ordenadas AS (
            SELECT
                id,
                first_value(id) OVER (
                    PARTITION BY convocatoria_id, ong_creadora_id
                    ORDER BY actualizada_en DESC, creada_en DESC, id DESC
                ) AS oferta_vigente_id
            FROM oferta
        )
        UPDATE oferta AS duplicada
        SET fusionada_en_oferta_id = ordenada.oferta_vigente_id
        FROM ofertas_ordenadas AS ordenada
        WHERE duplicada.id = ordenada.id
          AND duplicada.id <> ordenada.oferta_vigente_id;
        """
    )
    op.create_index(
        "uq_oferta_convocatoria_ong_vigente",
        "oferta",
        ["convocatoria_id", "ong_creadora_id"],
        unique=True,
        postgresql_where=sa.text("fusionada_en_oferta_id IS NULL"),
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

            IF EXISTS (
                SELECT 1
                FROM convocatoria_lote AS publicacion
                WHERE publicacion.convocatoria_id = NEW.convocatoria_id
                  AND publicacion.lote_id = NEW.lote_id
                  AND NEW.cantidad_ofrecida > publicacion.cantidad_publicada
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'La cantidad ofrecida supera la cantidad publicada',
                    CONSTRAINT = 'ck_oferta_item_cantidad_publicada';
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )


def downgrade() -> None:
    """Retira la unicidad y restaura la validación previa de los ítems."""

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
    op.drop_index(
        "uq_oferta_convocatoria_ong_vigente",
        table_name="oferta",
    )
    op.drop_constraint(
        op.f("ck_oferta_fusion_distinta"),
        "oferta",
        type_="check",
    )
    op.drop_constraint(
        op.f("fk_oferta_fusionada_en_oferta_id_oferta"),
        "oferta",
        type_="foreignkey",
    )
    op.drop_column("oferta", "fusionada_en_oferta_id")
