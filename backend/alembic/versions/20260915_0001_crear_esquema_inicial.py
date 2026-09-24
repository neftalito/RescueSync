"""Crear el esquema inicial de RescueSync.

Revision ID: 20260915_0001
Revises:
Create Date: 2026-09-15
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260915_0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


TIPO_ORGANIZACION = postgresql.ENUM(
    "MUNICIPIO",
    "CENTRO_COORDINADOR",
    "ONG",
    name="tipo_organizacion",
    create_type=False,
)
ROL_USUARIO = postgresql.ENUM(
    "OPERADOR_MUNICIPAL",
    "COORDINADOR_REGIONAL",
    "REPRESENTANTE_ONG",
    "AUDITOR_DIRECTIVO",
    name="rol_usuario",
    create_type=False,
)
GRAVEDAD_EMERGENCIA = postgresql.ENUM(
    "BAJA",
    "MEDIA",
    "ALTA",
    "CRITICA",
    name="gravedad_emergencia",
    create_type=False,
)
ESTADO_EMERGENCIA = postgresql.ENUM(
    "REGISTRADA",
    "EN_COORDINACION",
    "PUBLICADA",
    "EN_EVALUACION",
    "EN_EJECUCION",
    "RESUELTA",
    "CANCELADA",
    name="estado_emergencia",
    create_type=False,
)
ESTADO_SINCRONIZACION_BONITA = postgresql.ENUM(
    "PENDIENTE",
    "VINCULADA",
    "ERROR",
    "RESULTADO_DESCONOCIDO",
    name="estado_sincronizacion_bonita",
    create_type=False,
)
ESTADO_LOTE = postgresql.ENUM(
    "BORRADOR",
    "PUBLICADO",
    "CERRADO",
    "CANCELADO",
    name="estado_lote",
    create_type=False,
)
ESTADO_CONVOCATORIA = postgresql.ENUM(
    "ABIERTA",
    "CERRADA",
    "CANCELADA",
    name="estado_convocatoria",
    create_type=False,
)
ESTADO_OFERTA = postgresql.ENUM(
    "BORRADOR",
    "PRESENTADA",
    "EN_VALIDACION",
    "VALIDADA",
    "ADJUDICADA",
    "NO_ADJUDICADA",
    "RETIRADA",
    name="estado_oferta",
    create_type=False,
)
TIPO_APORTE = postgresql.ENUM(
    "RECURSO",
    "PERSONAL",
    "MIXTO",
    name="tipo_aporte",
    create_type=False,
)
TIPO_PARTICIPACION = postgresql.ENUM(
    "LIDER",
    "MIEMBRO",
    name="tipo_participacion",
    create_type=False,
)

ENUMS = (
    TIPO_ORGANIZACION,
    ROL_USUARIO,
    GRAVEDAD_EMERGENCIA,
    ESTADO_EMERGENCIA,
    ESTADO_SINCRONIZACION_BONITA,
    ESTADO_LOTE,
    ESTADO_CONVOCATORIA,
    ESTADO_OFERTA,
    TIPO_APORTE,
    TIPO_PARTICIPACION,
)


def upgrade() -> None:
    """Crea tablas, restricciones, índices y validaciones del dominio local."""

    bind = op.get_bind()
    for enum_type in ENUMS:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "organizacion",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("tipo", TIPO_ORGANIZACION, nullable=False),
        sa.Column("nombre", sa.String(length=160), nullable=False),
        sa.Column(
            "activa",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "actualizada_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(nombre) <> ''",
            name="nombre_no_vacio",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organizacion"),
    )
    op.create_index(
        "uq_organizacion_tipo_nombre",
        "organizacion",
        ["tipo", "nombre"],
        unique=True,
    )

    op.create_table(
        "usuario",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("organizacion_id", sa.BigInteger(), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("rol", ROL_USUARIO, nullable=False),
        sa.Column(
            "activo",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(email) <> ''",
            name="email_no_vacio",
        ),
        sa.CheckConstraint(
            "password_hash LIKE '$argon2%'",
            name="password_hash_argon2",
        ),
        sa.ForeignKeyConstraint(
            ["organizacion_id"],
            ["organizacion.id"],
            name="fk_usuario_organizacion_id_organizacion",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_usuario"),
    )
    op.create_index(
        "uq_usuario_email_normalizado",
        "usuario",
        [sa.text("lower(email)")],
        unique=True,
    )

    op.create_table(
        "emergencia",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("municipio_id", sa.BigInteger(), nullable=False),
        sa.Column("centro_coordinador_id", sa.BigInteger(), nullable=True),
        sa.Column("creada_por_usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("gravedad", GRAVEDAD_EMERGENCIA, nullable=False),
        sa.Column("zona", sa.String(length=255), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column(
            "estado",
            ESTADO_EMERGENCIA,
            server_default=sa.text("'REGISTRADA'::estado_emergencia"),
            nullable=False,
        ),
        sa.Column("bonita_process_definition_id", sa.BigInteger(), nullable=True),
        sa.Column("bonita_process_instance_id", sa.BigInteger(), nullable=True),
        sa.Column("bonita_process_version", sa.String(length=50), nullable=True),
        sa.Column(
            "bonita_sync",
            ESTADO_SINCRONIZACION_BONITA,
            server_default=sa.text("'PENDIENTE'::estado_sincronizacion_bonita"),
            nullable=False,
        ),
        sa.Column("bonita_ultimo_error", sa.Text(), nullable=True),
        sa.Column(
            "bonita_ultimo_intento_en",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "actualizada_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(zona) <> ''",
            name="zona_no_vacia",
        ),
        sa.CheckConstraint(
            "btrim(descripcion) <> ''",
            name="descripcion_no_vacia",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="version_positiva",
        ),
        sa.CheckConstraint(
            "bonita_process_definition_id IS NULL OR bonita_process_definition_id > 0",
            name="bonita_definition_id_positivo",
        ),
        sa.CheckConstraint(
            "bonita_process_instance_id IS NULL OR bonita_process_instance_id > 0",
            name="bonita_instance_id_positivo",
        ),
        sa.CheckConstraint(
            "bonita_sync <> 'VINCULADA' OR bonita_process_instance_id IS NOT NULL",
            name="bonita_vinculada_con_instancia",
        ),
        sa.ForeignKeyConstraint(
            ["centro_coordinador_id"],
            ["organizacion.id"],
            name="fk_emergencia_centro_coordinador_id_organizacion",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["creada_por_usuario_id"],
            ["usuario.id"],
            name="fk_emergencia_creada_por_usuario_id_usuario",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["municipio_id"],
            ["organizacion.id"],
            name="fk_emergencia_municipio_id_organizacion",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_emergencia"),
        sa.UniqueConstraint(
            "bonita_process_instance_id",
            name="uq_emergencia_bonita_process_instance_id",
        ),
    )
    op.create_index(
        "ix_emergencia_municipio_estado",
        "emergencia",
        ["municipio_id", "estado"],
        unique=False,
    )
    op.create_index(
        "ix_emergencia_centro_coordinador_estado",
        "emergencia",
        ["centro_coordinador_id", "estado"],
        unique=False,
    )
    op.create_index(
        "ix_emergencia_bonita_sync",
        "emergencia",
        ["bonita_sync"],
        unique=False,
    )

    op.create_table(
        "lote",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("emergencia_id", sa.BigInteger(), nullable=False),
        sa.Column("creado_por_usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo_necesidad", sa.String(length=120), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("cantidad_requerida", sa.Numeric(14, 3), nullable=False),
        sa.Column("unidad", sa.String(length=40), nullable=False),
        sa.Column(
            "estado",
            ESTADO_LOTE,
            server_default=sa.text("'BORRADOR'::estado_lote"),
            nullable=False,
        ),
        sa.Column(
            "version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "btrim(tipo_necesidad) <> ''",
            name="tipo_no_vacio",
        ),
        sa.CheckConstraint(
            "cantidad_requerida > 0",
            name="cantidad_positiva",
        ),
        sa.CheckConstraint(
            "btrim(unidad) <> ''",
            name="unidad_no_vacia",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="version_positiva",
        ),
        sa.ForeignKeyConstraint(
            ["creado_por_usuario_id"],
            ["usuario.id"],
            name="fk_lote_creado_por_usuario_id_usuario",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["emergencia_id"],
            ["emergencia.id"],
            name="fk_lote_emergencia_id_emergencia",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lote"),
    )
    op.create_index(
        "ix_lote_emergencia_estado",
        "lote",
        ["emergencia_id", "estado"],
        unique=False,
    )

    op.create_table(
        "convocatoria",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("emergencia_id", sa.BigInteger(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            ESTADO_CONVOCATORIA,
            server_default=sa.text("'ABIERTA'::estado_convocatoria"),
            nullable=False,
        ),
        sa.Column(
            "publicada_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("cierra_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cerrada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "numero > 0",
            name="numero_positivo",
        ),
        sa.CheckConstraint(
            "cierra_en > publicada_en",
            name="ventana_valida",
        ),
        sa.CheckConstraint(
            "estado <> 'CERRADA' OR cerrada_en IS NOT NULL",
            name="cerrada_con_fecha",
        ),
        sa.ForeignKeyConstraint(
            ["emergencia_id"],
            ["emergencia.id"],
            name="fk_convocatoria_emergencia_id_emergencia",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_convocatoria"),
        sa.UniqueConstraint(
            "emergencia_id",
            "numero",
            name="uq_convocatoria_emergencia_numero",
        ),
    )
    op.create_index(
        "ix_convocatoria_emergencia_estado",
        "convocatoria",
        ["emergencia_id", "estado"],
        unique=False,
    )
    op.create_index(
        "uq_convocatoria_abierta_por_emergencia",
        "convocatoria",
        ["emergencia_id"],
        unique=True,
        postgresql_where=sa.text("estado = 'ABIERTA'"),
    )

    op.create_table(
        "convocatoria_lote",
        sa.Column("convocatoria_id", sa.BigInteger(), nullable=False),
        sa.Column("lote_id", sa.BigInteger(), nullable=False),
        sa.Column("cantidad_publicada", sa.Numeric(14, 3), nullable=False),
        sa.Column("unidad_publicada", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "cantidad_publicada > 0",
            name="cantidad_positiva",
        ),
        sa.CheckConstraint(
            "btrim(unidad_publicada) <> ''",
            name="unidad_no_vacia",
        ),
        sa.ForeignKeyConstraint(
            ["convocatoria_id"],
            ["convocatoria.id"],
            name="fk_convocatoria_lote_convocatoria_id_convocatoria",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["lote_id"],
            ["lote.id"],
            name="fk_convocatoria_lote_lote_id_lote",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "convocatoria_id",
            "lote_id",
            name="pk_convocatoria_lote",
        ),
    )

    op.create_table(
        "oferta",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("convocatoria_id", sa.BigInteger(), nullable=False),
        sa.Column("ong_creadora_id", sa.BigInteger(), nullable=False),
        sa.Column("creada_por_usuario_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "estado",
            ESTADO_OFERTA,
            server_default=sa.text("'BORRADOR'::estado_oferta"),
            nullable=False,
        ),
        sa.Column(
            "version_actual",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "version_bloqueo",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "actualizada_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version_actual > 0",
            name="version_actual_positiva",
        ),
        sa.CheckConstraint(
            "version_bloqueo > 0",
            name="version_bloqueo_positiva",
        ),
        sa.ForeignKeyConstraint(
            ["convocatoria_id"],
            ["convocatoria.id"],
            name="fk_oferta_convocatoria_id_convocatoria",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["creada_por_usuario_id"],
            ["usuario.id"],
            name="fk_oferta_creada_por_usuario_id_usuario",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ong_creadora_id"],
            ["organizacion.id"],
            name="fk_oferta_ong_creadora_id_organizacion",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_oferta"),
    )
    op.create_index(
        "ix_oferta_convocatoria_estado",
        "oferta",
        ["convocatoria_id", "estado"],
        unique=False,
    )
    op.create_index(
        "ix_oferta_ong_estado",
        "oferta",
        ["ong_creadora_id", "estado"],
        unique=False,
    )

    op.create_table(
        "oferta_version",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("oferta_id", sa.BigInteger(), nullable=False),
        sa.Column("creada_por_usuario_id", sa.BigInteger(), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("presentada_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "creada_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "numero > 0",
            name="numero_positivo",
        ),
        sa.ForeignKeyConstraint(
            ["creada_por_usuario_id"],
            ["usuario.id"],
            name="fk_oferta_version_creada_por_usuario_id_usuario",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["oferta_id"],
            ["oferta.id"],
            name="fk_oferta_version_oferta_id_oferta",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_oferta_version"),
        sa.UniqueConstraint(
            "oferta_id",
            "numero",
            name="uq_oferta_version_oferta_numero",
        ),
    )
    op.create_index(
        "ix_oferta_version_oferta_numero_desc",
        "oferta_version",
        ["oferta_id", sa.text("numero DESC")],
        unique=False,
    )

    op.create_table(
        "oferta_item",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("oferta_version_id", sa.BigInteger(), nullable=False),
        sa.Column("convocatoria_id", sa.BigInteger(), nullable=False),
        sa.Column("lote_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo", TIPO_APORTE, nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("cantidad_ofrecida", sa.Numeric(14, 3), nullable=False),
        sa.Column("unidad", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "btrim(descripcion) <> ''",
            name="descripcion_no_vacia",
        ),
        sa.CheckConstraint(
            "cantidad_ofrecida > 0",
            name="cantidad_positiva",
        ),
        sa.CheckConstraint(
            "btrim(unidad) <> ''",
            name="unidad_no_vacia",
        ),
        sa.ForeignKeyConstraint(
            ["convocatoria_id", "lote_id"],
            [
                "convocatoria_lote.convocatoria_id",
                "convocatoria_lote.lote_id",
            ],
            name="fk_oferta_item_convocatoria_lote",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["oferta_version_id"],
            ["oferta_version.id"],
            name="fk_oferta_item_oferta_version_id_oferta_version",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_oferta_item"),
        sa.UniqueConstraint(
            "oferta_version_id",
            "lote_id",
            name="uq_oferta_item_version_lote",
        ),
    )
    op.create_index(
        "ix_oferta_item_lote",
        "oferta_item",
        ["lote_id"],
        unique=False,
    )

    op.create_table(
        "oferta_participante",
        sa.Column("oferta_id", sa.BigInteger(), nullable=False),
        sa.Column("ong_id", sa.BigInteger(), nullable=False),
        sa.Column("rol", TIPO_PARTICIPACION, nullable=False),
        sa.Column(
            "incorporada_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["oferta_id"],
            ["oferta.id"],
            name="fk_oferta_participante_oferta_id_oferta",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ong_id"],
            ["organizacion.id"],
            name="fk_oferta_participante_ong_id_organizacion",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "oferta_id",
            "ong_id",
            name="pk_oferta_participante",
        ),
    )
    op.create_index(
        "uq_oferta_participante_lider",
        "oferta_participante",
        ["oferta_id"],
        unique=True,
        postgresql_where=sa.text("rol = 'LIDER'"),
    )

    _create_integrity_triggers()


def downgrade() -> None:
    """Elimina de forma reversible el esquema local completo."""

    _drop_integrity_triggers()

    op.drop_index(
        "uq_oferta_participante_lider",
        table_name="oferta_participante",
    )
    op.drop_table("oferta_participante")
    op.drop_index("ix_oferta_item_lote", table_name="oferta_item")
    op.drop_table("oferta_item")
    op.drop_index(
        "ix_oferta_version_oferta_numero_desc",
        table_name="oferta_version",
    )
    op.drop_table("oferta_version")
    op.drop_index("ix_oferta_ong_estado", table_name="oferta")
    op.drop_index("ix_oferta_convocatoria_estado", table_name="oferta")
    op.drop_table("oferta")
    op.drop_table("convocatoria_lote")
    op.drop_index(
        "uq_convocatoria_abierta_por_emergencia",
        table_name="convocatoria",
    )
    op.drop_index(
        "ix_convocatoria_emergencia_estado",
        table_name="convocatoria",
    )
    op.drop_table("convocatoria")
    op.drop_index("ix_lote_emergencia_estado", table_name="lote")
    op.drop_table("lote")
    op.drop_index("ix_emergencia_bonita_sync", table_name="emergencia")
    op.drop_index(
        "ix_emergencia_centro_coordinador_estado",
        table_name="emergencia",
    )
    op.drop_index("ix_emergencia_municipio_estado", table_name="emergencia")
    op.drop_table("emergencia")
    op.drop_index("uq_usuario_email_normalizado", table_name="usuario")
    op.drop_table("usuario")
    op.drop_index("uq_organizacion_tipo_nombre", table_name="organizacion")
    op.drop_table("organizacion")

    bind = op.get_bind()
    for enum_type in reversed(ENUMS):
        enum_type.drop(bind, checkfirst=True)


def _create_integrity_triggers() -> None:
    """Agrega validaciones relacionales que un CHECK no puede expresar."""

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
    op.execute(
        """
        CREATE FUNCTION validar_emergencia_organizaciones()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM organizacion
                WHERE id = NEW.municipio_id AND tipo = 'MUNICIPIO'
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'La emergencia debe pertenecer a un municipio',
                    CONSTRAINT = 'ck_emergencia_municipio_tipo';
            END IF;

            IF NEW.centro_coordinador_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM organizacion
                WHERE id = NEW.centro_coordinador_id
                  AND tipo = 'CENTRO_COORDINADOR'
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'La organización asignada no es un centro coordinador',
                    CONSTRAINT = 'ck_emergencia_centro_coordinador_tipo';
            END IF;

            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_emergencia_organizaciones
        BEFORE INSERT OR UPDATE OF municipio_id, centro_coordinador_id ON emergencia
        FOR EACH ROW
        EXECUTE FUNCTION validar_emergencia_organizaciones();
        """
    )
    op.execute(
        """
        CREATE FUNCTION validar_convocatoria_lote_emergencia()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM convocatoria AS convocatoria_actual
                JOIN lote AS lote_actual
                  ON lote_actual.id = NEW.lote_id
                WHERE convocatoria_actual.id = NEW.convocatoria_id
                  AND convocatoria_actual.emergencia_id = lote_actual.emergencia_id
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'El lote no pertenece a la emergencia convocada',
                    CONSTRAINT = 'ck_convocatoria_lote_misma_emergencia';
            END IF;

            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_convocatoria_lote_emergencia
        BEFORE INSERT OR UPDATE OF convocatoria_id, lote_id ON convocatoria_lote
        FOR EACH ROW
        EXECUTE FUNCTION validar_convocatoria_lote_emergencia();
        """
    )
    op.execute(
        """
        CREATE FUNCTION validar_oferta_ong()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM organizacion
                WHERE id = NEW.ong_creadora_id AND tipo = 'ONG'
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'La organización creadora de la oferta debe ser una ONG',
                    CONSTRAINT = 'ck_oferta_ong_creadora_tipo';
            END IF;

            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_oferta_ong
        BEFORE INSERT OR UPDATE OF ong_creadora_id ON oferta
        FOR EACH ROW
        EXECUTE FUNCTION validar_oferta_ong();
        """
    )
    op.execute(
        """
        CREATE FUNCTION validar_oferta_item_convocatoria()
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
    op.execute(
        """
        CREATE FUNCTION validar_oferta_participante_ong()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM organizacion
                WHERE id = NEW.ong_id AND tipo = 'ONG'
            ) THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'Una participante de oferta debe ser una ONG',
                    CONSTRAINT = 'ck_oferta_participante_ong_tipo';
            END IF;

            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_oferta_participante_ong
        BEFORE INSERT OR UPDATE OF ong_id ON oferta_participante
        FOR EACH ROW
        EXECUTE FUNCTION validar_oferta_participante_ong();
        """
    )


def _drop_integrity_triggers() -> None:
    """Elimina las funciones y triggers antes de borrar sus tablas."""

    op.execute(
        "DROP TRIGGER IF EXISTS trg_oferta_participante_ong ON oferta_participante"
    )
    op.execute("DROP FUNCTION IF EXISTS validar_oferta_participante_ong()")
    op.execute("DROP TRIGGER IF EXISTS trg_oferta_item_convocatoria ON oferta_item")
    op.execute("DROP FUNCTION IF EXISTS validar_oferta_item_convocatoria()")
    op.execute("DROP TRIGGER IF EXISTS trg_oferta_ong ON oferta")
    op.execute("DROP FUNCTION IF EXISTS validar_oferta_ong()")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_convocatoria_lote_emergencia ON convocatoria_lote"
    )
    op.execute("DROP FUNCTION IF EXISTS validar_convocatoria_lote_emergencia()")
    op.execute("DROP TRIGGER IF EXISTS trg_emergencia_organizaciones ON emergencia")
    op.execute("DROP FUNCTION IF EXISTS validar_emergencia_organizaciones()")
    op.execute("DROP TRIGGER IF EXISTS trg_usuario_organizacion ON usuario")
    op.execute("DROP FUNCTION IF EXISTS validar_usuario_organizacion()")
