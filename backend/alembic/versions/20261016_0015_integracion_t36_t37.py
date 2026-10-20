"""Conservar evaluaciones, intenciones y confirmaciones nacionales T36/T37.

Revision ID: 20261016_0015
Revises: 20261015_0014
Create Date: 2026-10-16 13:27:51.351636
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261016_0015"
down_revision: str | Sequence[str] | None = "20261015_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea las entidades sin modificar datos existentes."""
    op.create_table(
        "comando_bonita",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("emergencia_id", sa.BigInteger(), nullable=False),
        sa.Column("usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("tarea", sa.String(length=160), nullable=False),
        sa.Column("actor", sa.String(length=80), nullable=False),
        sa.Column("correlacion", sa.String(length=120), nullable=False),
        sa.Column("contrato", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tarea_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "estado",
            postgresql.ENUM(
                "PENDIENTE",
                "EN_PROGRESO",
                "COMPLETADA",
                "ERROR",
                "RESULTADO_DESCONOCIDO",
                name="estado_tarea_bonita",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("claim_id", sa.Uuid(), nullable=True),
        sa.Column("intento_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["emergencia_id"],
            ["emergencia.id"],
            name=op.f("fk_comando_bonita_emergencia_id_emergencia"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuario.id"],
            name=op.f("fk_comando_bonita_usuario_id_usuario"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comando_bonita")),
        sa.UniqueConstraint("tarea_id", name=op.f("uq_comando_bonita_tarea_id")),
    )
    op.create_index(
        op.f("ix_comando_bonita_emergencia_id"),
        "comando_bonita",
        ["emergencia_id"],
        unique=False,
    )
    op.create_table(
        "operacion_nacional_sync",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("emergencia_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum(
                "COMPROMISO", "LIBERACION", "CIERRE", name="tipo_operacion_nacional"
            ),
            nullable=False,
        ),
        sa.Column(
            "estado",
            sa.Enum(
                "PENDIENTE",
                "INCIERTO",
                "TEMPORAL",
                "CONFIGURACION",
                "RECHAZO_DEFINITIVO",
                "CONFIRMADA",
                name="estado_operacion_nacional",
            ),
            nullable=False,
        ),
        sa.Column("clave", sa.String(length=120), nullable=False),
        sa.Column("huella", sa.String(length=64), nullable=False),
        sa.Column("request", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "confirmacion", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("resultado", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["emergencia_id"],
            ["emergencia.id"],
            name=op.f("fk_operacion_nacional_sync_emergencia_id_emergencia"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operacion_nacional_sync")),
        sa.UniqueConstraint("clave", name=op.f("uq_operacion_nacional_sync_clave")),
    )
    op.create_index(
        "ix_operacion_nacional_emergencia_estado",
        "operacion_nacional_sync",
        ["emergencia_id", "estado"],
        unique=False,
    )
    op.create_table(
        "evaluacion_local",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("emergencia_id", sa.BigInteger(), nullable=False),
        sa.Column("convocatoria_id", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("huella_snapshot", sa.String(length=64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resultado", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cobertura", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "revision > 0", name=op.f("ck_evaluacion_local_revision_positiva")
        ),
        sa.ForeignKeyConstraint(
            ["convocatoria_id"],
            ["convocatoria.id"],
            name=op.f("fk_evaluacion_local_convocatoria_id_convocatoria"),
        ),
        sa.ForeignKeyConstraint(
            ["emergencia_id"],
            ["emergencia.id"],
            name=op.f("fk_evaluacion_local_emergencia_id_emergencia"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluacion_local")),
        sa.UniqueConstraint(
            "convocatoria_id",
            "revision",
            name=op.f("uq_evaluacion_local_convocatoria_id"),
        ),
    )
    op.create_table(
        "adjudicacion_local",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("convocatoria_id", sa.BigInteger(), nullable=False),
        sa.Column("evaluacion_id", sa.Uuid(), nullable=False),
        sa.Column("operacion_id", sa.Uuid(), nullable=False),
        sa.Column("seleccion", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("estado", sa.String(length=30), nullable=False),
        sa.Column("proyecto_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE_COMPROMISO','CONFIRMADA','REQUIERE_REVISION')",
            name=op.f("ck_adjudicacion_local_estado_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["convocatoria_id"],
            ["convocatoria.id"],
            name=op.f("fk_adjudicacion_local_convocatoria_id_convocatoria"),
        ),
        sa.ForeignKeyConstraint(
            ["evaluacion_id"],
            ["evaluacion_local.id"],
            name=op.f("fk_adjudicacion_local_evaluacion_id_evaluacion_local"),
        ),
        sa.ForeignKeyConstraint(
            ["id"],
            ["comando_bonita.id"],
            name=op.f("fk_adjudicacion_local_id_comando_bonita"),
        ),
        sa.ForeignKeyConstraint(
            ["operacion_id"],
            ["operacion_nacional_sync.id"],
            name=op.f("fk_adjudicacion_local_operacion_id_operacion_nacional_sync"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_adjudicacion_local")),
        sa.UniqueConstraint(
            "operacion_id", name=op.f("uq_adjudicacion_local_operacion_id")
        ),
    )
    op.create_index(
        "uq_adjudicacion_efectiva_ronda",
        "adjudicacion_local",
        ["convocatoria_id"],
        unique=True,
        postgresql_where=sa.text("estado <> 'REQUIERE_REVISION'"),
    )
    op.create_table(
        "decision_evaluacion",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluacion_id", sa.Uuid(), nullable=False),
        sa.Column("contenido", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["evaluacion_id"],
            ["evaluacion_local.id"],
            name=op.f("fk_decision_evaluacion_evaluacion_id_evaluacion_local"),
        ),
        sa.ForeignKeyConstraint(
            ["id"],
            ["comando_bonita.id"],
            name=op.f("fk_decision_evaluacion_id_comando_bonita"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision_evaluacion")),
        sa.UniqueConstraint(
            "evaluacion_id", name=op.f("uq_decision_evaluacion_evaluacion_id")
        ),
    )
    op.create_table(
        "participacion_adjudicada",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("adjudicacion_id", sa.Uuid(), nullable=False),
        sa.Column("ong_id", sa.BigInteger(), nullable=False),
        sa.Column("ong_nacional_id", sa.Uuid(), nullable=False),
        sa.Column("estado", sa.String(length=30), nullable=False),
        sa.CheckConstraint(
            "estado IN ('EN_EJECUCION','FINALIZACION_SOLICITADA','LIBERADA')",
            name=op.f("ck_participacion_adjudicada_estado_valido"),
        ),
        sa.ForeignKeyConstraint(
            ["adjudicacion_id"],
            ["adjudicacion_local.id"],
            name=op.f("fk_participacion_adjudicada_adjudicacion_id_adjudicacion_local"),
        ),
        sa.ForeignKeyConstraint(
            ["ong_id"],
            ["organizacion.id"],
            name=op.f("fk_participacion_adjudicada_ong_id_organizacion"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_participacion_adjudicada")),
        sa.UniqueConstraint(
            "adjudicacion_id", "ong_id", name="uq_participacion_ong_local"
        ),
        sa.UniqueConstraint(
            "adjudicacion_id", "ong_nacional_id", name="uq_participacion_ong_nacional"
        ),
    )
    op.create_table(
        "solicitud_cierre",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("adjudicacion_id", sa.Uuid(), nullable=False),
        sa.Column("operacion_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["adjudicacion_id"],
            ["adjudicacion_local.id"],
            name=op.f("fk_solicitud_cierre_adjudicacion_id_adjudicacion_local"),
        ),
        sa.ForeignKeyConstraint(
            ["id"],
            ["comando_bonita.id"],
            name=op.f("fk_solicitud_cierre_id_comando_bonita"),
        ),
        sa.ForeignKeyConstraint(
            ["operacion_id"],
            ["operacion_nacional_sync.id"],
            name=op.f("fk_solicitud_cierre_operacion_id_operacion_nacional_sync"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_solicitud_cierre")),
        sa.UniqueConstraint(
            "adjudicacion_id", name=op.f("uq_solicitud_cierre_adjudicacion_id")
        ),
        sa.UniqueConstraint(
            "operacion_id", name=op.f("uq_solicitud_cierre_operacion_id")
        ),
    )
    op.create_table(
        "compromiso_nacional_local",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("participacion_id", sa.Uuid(), nullable=False),
        sa.Column("detalle", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("liberacion_id", sa.Uuid(), nullable=True),
        sa.Column("liberado_en", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["liberacion_id"],
            ["operacion_nacional_sync.id"],
            name=op.f(
                "fk_compromiso_nacional_local_liberacion_id_operacion_nacional_sync"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["participacion_id"],
            ["participacion_adjudicada.id"],
            name=op.f(
                "fk_compromiso_nacional_local_participacion_id_participacion_adjudicada"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_compromiso_nacional_local")),
        sa.UniqueConstraint(
            "liberacion_id", name=op.f("uq_compromiso_nacional_local_liberacion_id")
        ),
    )
    op.create_index(
        op.f("ix_compromiso_nacional_local_participacion_id"),
        "compromiso_nacional_local",
        ["participacion_id"],
        unique=False,
    )
    op.create_table(
        "finalizacion_ong",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("participacion_id", sa.Uuid(), nullable=False),
        sa.Column(
            "solicitada_en",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["id"],
            ["comando_bonita.id"],
            name=op.f("fk_finalizacion_ong_id_comando_bonita"),
        ),
        sa.ForeignKeyConstraint(
            ["participacion_id"],
            ["participacion_adjudicada.id"],
            name=op.f("fk_finalizacion_ong_participacion_id_participacion_adjudicada"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finalizacion_ong")),
        sa.UniqueConstraint(
            "participacion_id", name=op.f("uq_finalizacion_ong_participacion_id")
        ),
    )

    op.execute("""
        CREATE FUNCTION proteger_intencion_nacional() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE campo text;
        BEGIN
            FOREACH campo IN ARRAY string_to_array(TG_ARGV[0], ',') LOOP
                IF to_jsonb(NEW)->campo IS DISTINCT FROM to_jsonb(OLD)->campo THEN
                    RAISE EXCEPTION 'La intención nacional es inmutable' USING ERRCODE = '23514';
                END IF;
            END LOOP;
            IF TG_NARGS > 1 THEN
                FOREACH campo IN ARRAY string_to_array(TG_ARGV[1], ',') LOOP
                    IF to_jsonb(OLD)->campo IS NOT NULL AND to_jsonb(OLD)->campo <> 'null'::jsonb
                       AND to_jsonb(NEW)->campo IS DISTINCT FROM to_jsonb(OLD)->campo THEN
                        RAISE EXCEPTION 'La confirmación nacional es inmutable' USING ERRCODE = '23514';
                    END IF;
                END LOOP;
            END IF;
            RETURN NEW;
        END $$
    """)
    op.execute(
        "CREATE TRIGGER proteger_evaluacion_local BEFORE UPDATE ON evaluacion_local FOR EACH ROW EXECUTE FUNCTION proteger_intencion_nacional('id,emergencia_id,convocatoria_id,revision,huella_snapshot,snapshot,creada_en','resultado,cobertura')"
    )
    op.execute(
        "CREATE TRIGGER proteger_comando_bonita BEFORE UPDATE ON comando_bonita FOR EACH ROW EXECUTE FUNCTION proteger_intencion_nacional('id,emergencia_id,usuario_id,tarea,actor,correlacion,contrato','tarea_id')"
    )
    op.execute(
        "CREATE TRIGGER proteger_operacion_nacional_sync BEFORE UPDATE ON operacion_nacional_sync FOR EACH ROW EXECUTE FUNCTION proteger_intencion_nacional('id,emergencia_id,tipo,clave,huella,request','confirmacion')"
    )
    op.execute(
        "CREATE TRIGGER proteger_adjudicacion_local BEFORE UPDATE ON adjudicacion_local FOR EACH ROW EXECUTE FUNCTION proteger_intencion_nacional('id,convocatoria_id,evaluacion_id,operacion_id,seleccion','proyecto_id')"
    )
    op.execute(
        "CREATE TRIGGER proteger_decision_evaluacion BEFORE UPDATE ON decision_evaluacion FOR EACH ROW EXECUTE FUNCTION proteger_intencion_nacional('id,evaluacion_id,contenido','')"
    )
    op.execute(
        "CREATE TRIGGER proteger_participacion_adjudicada BEFORE UPDATE ON participacion_adjudicada FOR EACH ROW EXECUTE FUNCTION proteger_intencion_nacional('id,adjudicacion_id,ong_id,ong_nacional_id','')"
    )
    op.execute(
        "CREATE TRIGGER proteger_compromiso_nacional_local BEFORE UPDATE ON compromiso_nacional_local FOR EACH ROW EXECUTE FUNCTION proteger_intencion_nacional('id,participacion_id,detalle','liberacion_id,liberado_en')"
    )
    op.execute(
        "CREATE TRIGGER proteger_finalizacion_ong BEFORE UPDATE ON finalizacion_ong FOR EACH ROW EXECUTE FUNCTION proteger_intencion_nacional('id,participacion_id,solicitada_en','')"
    )
    op.execute(
        "CREATE TRIGGER proteger_solicitud_cierre BEFORE UPDATE ON solicitud_cierre FOR EACH ROW EXECUTE FUNCTION proteger_intencion_nacional('id,adjudicacion_id,operacion_id','')"
    )


def downgrade() -> None:
    """Elimina sólo las entidades de esta revisión y sus tipos propios."""
    op.drop_table("finalizacion_ong")
    op.drop_index(
        op.f("ix_compromiso_nacional_local_participacion_id"),
        table_name="compromiso_nacional_local",
    )
    op.drop_table("compromiso_nacional_local")
    op.drop_table("solicitud_cierre")
    op.drop_table("participacion_adjudicada")
    op.drop_table("decision_evaluacion")
    op.drop_index(
        "uq_adjudicacion_efectiva_ronda",
        table_name="adjudicacion_local",
        postgresql_where=sa.text("estado <> 'REQUIERE_REVISION'"),
    )
    op.drop_table("adjudicacion_local")
    op.drop_table("evaluacion_local")
    op.drop_index(
        "ix_operacion_nacional_emergencia_estado", table_name="operacion_nacional_sync"
    )
    op.drop_table("operacion_nacional_sync")
    op.drop_index(op.f("ix_comando_bonita_emergencia_id"), table_name="comando_bonita")
    op.drop_table("comando_bonita")

    postgresql.ENUM(name="estado_operacion_nacional").drop(op.get_bind())
    postgresql.ENUM(name="tipo_operacion_nacional").drop(op.get_bind())
    op.execute("DROP FUNCTION IF EXISTS proteger_intencion_nacional()")
