"""Agregar administración de usuarios y versionado de sesiones.

Revision ID: 20260917_0002
Revises: 20260915_0001
Create Date: 2026-09-17
"""

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_0002"
down_revision: str | None = "20260915_0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Agrega el rol administrador y el control de credenciales temporales."""

    op.execute("ALTER TYPE rol_usuario ADD VALUE IF NOT EXISTS 'ADMINISTRADOR'")
    op.add_column(
        "usuario",
        sa.Column(
            "requiere_cambio_password",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "usuario",
        sa.Column(
            "version_sesion",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "version_sesion_positiva",
        "usuario",
        "version_sesion > 0",
    )
    _crear_trigger_usuario_con_administrador()


def downgrade() -> None:
    """Retira la administración convirtiendo esas cuentas en auditoras."""

    op.execute("DROP TRIGGER IF EXISTS trg_usuario_organizacion ON usuario")
    op.execute("DROP FUNCTION IF EXISTS validar_usuario_organizacion()")
    op.execute(
        "UPDATE usuario SET rol = 'AUDITOR_DIRECTIVO' WHERE rol::text = 'ADMINISTRADOR'"
    )
    op.drop_constraint(
        op.f("ck_usuario_version_sesion_positiva"),
        "usuario",
        type_="check",
    )
    op.drop_column("usuario", "version_sesion")
    op.drop_column("usuario", "requiere_cambio_password")

    op.execute("ALTER TABLE usuario ALTER COLUMN rol TYPE varchar(64) USING rol::text")
    op.execute("DROP TYPE rol_usuario")
    op.execute(
        "CREATE TYPE rol_usuario AS ENUM ("
        "'OPERADOR_MUNICIPAL', "
        "'COORDINADOR_REGIONAL', "
        "'REPRESENTANTE_ONG', "
        "'AUDITOR_DIRECTIVO')"
    )
    op.execute(
        "ALTER TABLE usuario ALTER COLUMN rol TYPE rol_usuario USING rol::rol_usuario"
    )
    _crear_trigger_usuario_original()


def _crear_trigger_usuario_con_administrador() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validar_usuario_organizacion()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            tipo_actual tipo_organizacion;
            tipo_esperado tipo_organizacion;
        BEGIN
            IF NEW.rol::text IN ('AUDITOR_DIRECTIVO', 'ADMINISTRADOR') THEN
                IF NEW.organizacion_id IS NOT NULL THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '23514',
                        MESSAGE = 'El rol no admite una organización',
                        CONSTRAINT = 'ck_usuario_rol_organizacion';
                END IF;
                RETURN NEW;
            END IF;

            IF NEW.organizacion_id IS NULL THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'El rol requiere una organización',
                    CONSTRAINT = 'ck_usuario_rol_organizacion';
            END IF;

            tipo_esperado := CASE NEW.rol::text
                WHEN 'OPERADOR_MUNICIPAL' THEN 'MUNICIPIO'::tipo_organizacion
                WHEN 'COORDINADOR_REGIONAL' THEN 'CENTRO_COORDINADOR'::tipo_organizacion
                WHEN 'REPRESENTANTE_ONG' THEN 'ONG'::tipo_organizacion
            END;

            SELECT tipo INTO tipo_actual
            FROM organizacion
            WHERE id = NEW.organizacion_id;

            IF FOUND AND tipo_actual <> tipo_esperado THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'El rol no corresponde al tipo de organización',
                    CONSTRAINT = 'ck_usuario_rol_organizacion';
            END IF;

            RETURN NEW;
        END;
        $$;

        DROP TRIGGER IF EXISTS trg_usuario_organizacion ON usuario;
        CREATE TRIGGER trg_usuario_organizacion
        BEFORE INSERT OR UPDATE OF organizacion_id, rol ON usuario
        FOR EACH ROW
        EXECUTE FUNCTION validar_usuario_organizacion();
        """
    )


def _crear_trigger_usuario_original() -> None:
    op.execute(
        """
        CREATE FUNCTION validar_usuario_organizacion()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            tipo_actual tipo_organizacion;
            tipo_esperado tipo_organizacion;
        BEGIN
            IF NEW.rol = 'AUDITOR_DIRECTIVO' THEN
                RETURN NEW;
            END IF;

            IF NEW.organizacion_id IS NULL THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'El rol requiere una organización',
                    CONSTRAINT = 'ck_usuario_rol_organizacion';
            END IF;

            tipo_esperado := CASE NEW.rol
                WHEN 'OPERADOR_MUNICIPAL' THEN 'MUNICIPIO'::tipo_organizacion
                WHEN 'COORDINADOR_REGIONAL' THEN 'CENTRO_COORDINADOR'::tipo_organizacion
                WHEN 'REPRESENTANTE_ONG' THEN 'ONG'::tipo_organizacion
            END;

            SELECT tipo INTO tipo_actual
            FROM organizacion
            WHERE id = NEW.organizacion_id;

            IF FOUND AND tipo_actual <> tipo_esperado THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'El rol no corresponde al tipo de organización',
                    CONSTRAINT = 'ck_usuario_rol_organizacion';
            END IF;

            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_usuario_organizacion
        BEFORE INSERT OR UPDATE OF organizacion_id, rol ON usuario
        FOR EACH ROW
        EXECUTE FUNCTION validar_usuario_organizacion();
        """
    )
