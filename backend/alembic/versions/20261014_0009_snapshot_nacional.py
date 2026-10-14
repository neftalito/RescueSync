"""Versionar requerimientos, participantes y aportes nacionales sin inferir historia.

Revision ID: 20261014_0009
Revises: 20261008_0008
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261014_0009"
down_revision: str | None = "20261008_0008"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    riesgo = postgresql.ENUM(
        "BAJA",
        "MEDIA",
        "ALTA",
        "CRITICA",
        name="gravedad_emergencia",
        create_type=False,
    )
    rol = postgresql.ENUM(
        "LIDER", "MIEMBRO", name="tipo_participacion", create_type=False
    )
    for tabla, nombres in (
        (
            "lote",
            (
                "capacidad_nacional_id",
                "codigo_capacidad",
                "admite_fracciones",
                "riesgo_requerido",
            ),
        ),
        (
            "convocatoria_lote",
            (
                "capacidad_nacional_id",
                "codigo_capacidad_publicada",
                "admite_fracciones_publicada",
                "riesgo_requerido_publicado",
            ),
        ),
    ):
        for nombre, tipo in zip(
            nombres, (sa.Uuid(), sa.String(80), sa.Boolean(), riesgo), strict=True
        ):
            op.add_column(tabla, sa.Column(nombre, tipo, nullable=True))
    op.add_column(
        "convocatoria", sa.Column("sistema_origen_ref", sa.String(80), nullable=True)
    )
    op.add_column(
        "convocatoria", sa.Column("gravedad_publicada", riesgo, nullable=True)
    )
    op.add_column(
        "oferta_version",
        sa.Column(
            "requiere_desglose_nacional",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_oferta_item_id_version", "oferta_item", ["id", "oferta_version_id"]
    )
    op.create_table(
        "oferta_version_participante",
        sa.Column(
            "oferta_version_id",
            sa.BigInteger(),
            sa.ForeignKey("oferta_version.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "ong_id",
            sa.BigInteger(),
            sa.ForeignKey("organizacion.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("ong_nacional_id", sa.Uuid(), nullable=True),
        sa.Column("nombre_ong", sa.String(160), nullable=False),
        sa.Column("rol", rol, nullable=False),
        sa.Column("confirmada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "version_origen_id",
            sa.BigInteger(),
            sa.ForeignKey("oferta_version.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "uq_oferta_version_participante_lider",
        "oferta_version_participante",
        ["oferta_version_id"],
        unique=True,
        postgresql_where=sa.text("rol = 'LIDER'"),
    )
    op.create_table(
        "oferta_item_aporte",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("oferta_item_id", sa.BigInteger(), nullable=False),
        sa.Column("oferta_version_id", sa.BigInteger(), nullable=False),
        sa.Column("ong_id", sa.BigInteger(), nullable=False),
        sa.Column("recurso_nacional_id", sa.Uuid(), nullable=False),
        sa.Column("capacidad_nacional_id", sa.Uuid(), nullable=False),
        sa.Column("cantidad", sa.Numeric(14, 3), nullable=False),
        sa.Column("unidad", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(
            ["oferta_item_id", "oferta_version_id"],
            ["oferta_item.id", "oferta_item.oferta_version_id"],
            name="fk_aporte_item_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["oferta_version_id", "ong_id"],
            [
                "oferta_version_participante.oferta_version_id",
                "oferta_version_participante.ong_id",
            ],
            name="fk_aporte_participante_version",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "oferta_item_id",
            "ong_id",
            "recurso_nacional_id",
            name="uq_aporte_item_ong_recurso",
        ),
        sa.CheckConstraint(
            "cantidad > 0 AND cantidad < 'Infinity'::numeric",
            name="ck_aporte_cantidad_finita",
        ),
        sa.CheckConstraint("btrim(unidad) <> ''", name="ck_aporte_unidad"),
    )
    op.create_index(
        "ix_aporte_recurso_nacional", "oferta_item_aporte", ["recurso_nacional_id"]
    )
    op.execute(INTEGRIDAD)


INTEGRIDAD = """
CREATE FUNCTION local_validar_desglose() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v bigint;
BEGIN
    IF TG_TABLE_NAME = 'oferta_version' THEN v := COALESCE(NEW.id, OLD.id);
    ELSE v := COALESCE(NEW.oferta_version_id, OLD.oferta_version_id); END IF;
    IF NOT EXISTS (SELECT 1 FROM oferta_version WHERE id = v AND requiere_desglose_nacional AND presentada_en IS NOT NULL) THEN RETURN NULL; END IF;
    IF (SELECT count(*) FROM oferta_version_participante WHERE oferta_version_id = v AND rol = 'LIDER') <> 1
       OR EXISTS (SELECT 1 FROM oferta_version_participante WHERE oferta_version_id = v AND (ong_nacional_id IS NULL OR confirmada_en IS NULL))
       OR NOT EXISTS (SELECT 1 FROM oferta_item WHERE oferta_version_id = v)
       OR EXISTS (
           SELECT 1 FROM oferta_item i JOIN convocatoria_lote l ON l.convocatoria_id = i.convocatoria_id AND l.lote_id = i.lote_id
           WHERE i.oferta_version_id = v AND (
               l.capacidad_nacional_id IS NULL OR l.codigo_capacidad_publicada IS NULL OR l.admite_fracciones_publicada IS NULL OR l.riesgo_requerido_publicado IS NULL
               OR i.cantidad_ofrecida <> COALESCE((SELECT sum(a.cantidad) FROM oferta_item_aporte a WHERE a.oferta_item_id = i.id), 0)
               OR EXISTS (SELECT 1 FROM oferta_item_aporte a WHERE a.oferta_item_id = i.id AND (a.capacidad_nacional_id <> l.capacidad_nacional_id OR a.unidad <> l.unidad_publicada OR (NOT l.admite_fracciones_publicada AND a.cantidad <> trunc(a.cantidad))))
           )
       ) THEN RAISE EXCEPTION 'La version presentada requiere referencias y desglose completo' USING ERRCODE='23514', CONSTRAINT='ck_version_desglose_completo'; END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER validar_desglose_version AFTER INSERT OR UPDATE ON oferta_version DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION local_validar_desglose();
CREATE CONSTRAINT TRIGGER validar_desglose_participante AFTER INSERT OR UPDATE OR DELETE ON oferta_version_participante DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION local_validar_desglose();
CREATE CONSTRAINT TRIGGER validar_desglose_item AFTER INSERT OR UPDATE OR DELETE ON oferta_item DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION local_validar_desglose();
CREATE CONSTRAINT TRIGGER validar_desglose_aporte AFTER INSERT OR UPDATE OR DELETE ON oferta_item_aporte DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION local_validar_desglose();

CREATE FUNCTION local_proteger_version_nacional() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v bigint;
BEGIN
    IF TG_TABLE_NAME = 'oferta_version' THEN
        IF OLD.requiere_desglose_nacional AND (NEW.requiere_desglose_nacional IS DISTINCT FROM OLD.requiere_desglose_nacional OR (OLD.presentada_en IS NOT NULL AND NEW IS DISTINCT FROM OLD)) THEN
            RAISE EXCEPTION 'El contenido presentado es inmutable' USING ERRCODE='23514', CONSTRAINT='ck_version_nacional_inmutable';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP <> 'INSERT' AND EXISTS (SELECT 1 FROM oferta_version WHERE id = OLD.oferta_version_id AND requiere_desglose_nacional AND presentada_en IS NOT NULL) THEN
        RAISE EXCEPTION 'El contenido presentado es inmutable' USING ERRCODE='23514', CONSTRAINT='ck_version_nacional_inmutable';
    END IF;
    v := CASE WHEN TG_OP = 'DELETE' THEN OLD.oferta_version_id ELSE NEW.oferta_version_id END;
    IF EXISTS (SELECT 1 FROM oferta_version WHERE id = v AND requiere_desglose_nacional AND presentada_en IS NOT NULL) THEN
        RAISE EXCEPTION 'El contenido presentado es inmutable' USING ERRCODE='23514', CONSTRAINT='ck_version_nacional_inmutable';
    END IF;
    RETURN COALESCE(NEW, OLD);
END $$;
CREATE TRIGGER proteger_version_nacional BEFORE UPDATE ON oferta_version FOR EACH ROW EXECUTE FUNCTION local_proteger_version_nacional();
CREATE TRIGGER proteger_item_nacional BEFORE INSERT OR UPDATE OR DELETE ON oferta_item FOR EACH ROW EXECUTE FUNCTION local_proteger_version_nacional();
CREATE TRIGGER proteger_participante_nacional BEFORE INSERT OR UPDATE OR DELETE ON oferta_version_participante FOR EACH ROW EXECUTE FUNCTION local_proteger_version_nacional();
CREATE TRIGGER proteger_aporte_nacional BEFORE INSERT OR UPDATE OR DELETE ON oferta_item_aporte FOR EACH ROW EXECUTE FUNCTION local_proteger_version_nacional();

CREATE FUNCTION local_proteger_requerimiento() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.capacidad_nacional_id IS NOT NULL AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'El requerimiento publicado es inmutable' USING ERRCODE='23514', CONSTRAINT='ck_requerimiento_nacional_inmutable';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER proteger_requerimiento BEFORE UPDATE ON convocatoria_lote FOR EACH ROW EXECUTE FUNCTION local_proteger_requerimiento();

CREATE FUNCTION local_proteger_cabecera_convocatoria() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF (OLD.gravedad_publicada IS NOT NULL OR OLD.sistema_origen_ref IS NOT NULL)
       AND (NEW.gravedad_publicada IS DISTINCT FROM OLD.gravedad_publicada OR NEW.sistema_origen_ref IS DISTINCT FROM OLD.sistema_origen_ref) THEN
        RAISE EXCEPTION 'La cabecera publicada es inmutable' USING ERRCODE='23514', CONSTRAINT='ck_convocatoria_nacional_inmutable';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER proteger_cabecera_convocatoria BEFORE UPDATE ON convocatoria FOR EACH ROW EXECUTE FUNCTION local_proteger_cabecera_convocatoria();
"""


def downgrade() -> None:
    for funcion in (
        "local_proteger_requerimiento",
        "local_proteger_cabecera_convocatoria",
        "local_proteger_version_nacional",
        "local_validar_desglose",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {funcion}() CASCADE")
    op.drop_table("oferta_item_aporte")
    op.drop_table("oferta_version_participante")
    op.drop_constraint("uq_oferta_item_id_version", "oferta_item", type_="unique")
    op.drop_column("oferta_version", "requiere_desglose_nacional")
    op.drop_column("convocatoria", "sistema_origen_ref")
    op.drop_column("convocatoria", "gravedad_publicada")
    for tabla, nombres in (
        (
            "lote",
            (
                "capacidad_nacional_id",
                "codigo_capacidad",
                "admite_fracciones",
                "riesgo_requerido",
            ),
        ),
        (
            "convocatoria_lote",
            (
                "capacidad_nacional_id",
                "codigo_capacidad_publicada",
                "admite_fracciones_publicada",
                "riesgo_requerido_publicado",
            ),
        ),
    ):
        for nombre in reversed(nombres):
            op.drop_column(tabla, nombre)
