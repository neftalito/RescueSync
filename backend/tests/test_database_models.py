from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from psycopg import Error as PsycopgError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import (
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    EstadoEmergencia,
    EstadoLote,
    EstadoOferta,
    EstadoSincronizacionBonita,
    GravedadEmergencia,
    Lote,
    Oferta,
    OfertaItem,
    OfertaParticipante,
    OfertaVersion,
    Organizacion,
    RolUsuario,
    TipoAporte,
    TipoOrganizacion,
    TipoParticipacion,
    Usuario,
)

ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


def _crear_organizacion(
    session: Session,
    tipo: TipoOrganizacion,
    nombre: str,
) -> Organizacion:
    organizacion = Organizacion(tipo=tipo, nombre=nombre)
    session.add(organizacion)
    session.flush()
    return organizacion


def _crear_usuario(
    session: Session,
    organizacion: Organizacion | None,
    rol: RolUsuario,
    email: str,
) -> Usuario:
    usuario = Usuario(
        organizacion_id=organizacion.id if organizacion else None,
        email=email,
        password_hash=ARGON2_HASH,
        rol=rol,
    )
    session.add(usuario)
    session.flush()
    return usuario


def _crear_emergencia(
    session: Session,
    municipio: Organizacion,
    operador: Usuario,
    zona: str,
    centro_coordinador: Organizacion | None = None,
) -> Emergencia:
    emergencia = Emergencia(
        municipio_id=municipio.id,
        centro_coordinador_id=(
            centro_coordinador.id if centro_coordinador is not None else None
        ),
        creada_por_usuario_id=operador.id,
        gravedad=GravedadEmergencia.ALTA,
        zona=zona,
        descripcion="Inundación con familias evacuadas",
    )
    session.add(emergencia)
    session.flush()
    return emergencia


def _crear_lote(
    session: Session,
    emergencia: Emergencia,
    creador: Usuario,
    tipo_necesidad: str,
) -> Lote:
    lote = Lote(
        emergencia_id=emergencia.id,
        creado_por_usuario_id=creador.id,
        tipo_necesidad=tipo_necesidad,
        descripcion="Necesidad prioritaria",
        cantidad_requerida=Decimal(1000),
        unidad="raciones",
    )
    session.add(lote)
    session.flush()
    return lote


def _crear_convocatoria(
    session: Session,
    emergencia: Emergencia,
    numero: int,
    estado: EstadoConvocatoria = EstadoConvocatoria.ABIERTA,
) -> Convocatoria:
    ahora = datetime.now(UTC)
    if estado is EstadoConvocatoria.CERRADA:
        publicada_en = ahora - timedelta(hours=4)
        cierra_en = ahora - timedelta(hours=2)
        cerrada_en = ahora - timedelta(hours=1)
    else:
        publicada_en = ahora
        cierra_en = ahora + timedelta(hours=2)
        cerrada_en = None

    convocatoria = Convocatoria(
        emergencia_id=emergencia.id,
        numero=numero,
        estado=estado,
        publicada_en=publicada_en,
        cierra_en=cierra_en,
        cerrada_en=cerrada_en,
    )
    session.add(convocatoria)
    session.flush()
    return convocatoria


def _publicar_lote(
    session: Session,
    convocatoria: Convocatoria,
    lote: Lote,
) -> ConvocatoriaLote:
    lote.estado = EstadoLote.PUBLICADO
    publicacion = ConvocatoriaLote(
        convocatoria_id=convocatoria.id,
        lote_id=lote.id,
        cantidad_publicada=lote.cantidad_requerida,
        unidad_publicada=lote.unidad,
    )
    session.add(publicacion)
    session.flush()
    return publicacion


def _crear_oferta(
    session: Session,
    convocatoria: Convocatoria,
    ong: Organizacion,
    representante: Usuario,
) -> tuple[Oferta, OfertaVersion]:
    oferta = Oferta(
        convocatoria_id=convocatoria.id,
        ong_creadora_id=ong.id,
        creada_por_usuario_id=representante.id,
        estado=EstadoOferta.PRESENTADA,
    )
    session.add(oferta)
    session.flush()

    version = OfertaVersion(
        oferta_id=oferta.id,
        creada_por_usuario_id=representante.id,
        numero=1,
        presentada_en=datetime.now(UTC),
    )
    session.add(version)
    session.flush()
    return oferta, version


def _assert_restriccion(
    error: pytest.ExceptionInfo[IntegrityError], nombre: str
) -> None:
    assert isinstance(error.value.orig, PsycopgError)
    assert error.value.orig.diag.constraint_name == nombre


def test_metadata_registra_todo_el_esquema() -> None:
    assert set(Base.metadata.tables) == {
        "aprovisionamiento_nacional",
        "oferta_version_participante",
        "oferta_item_aporte",
        "conexion_nacional",
        "acceso_nacional",
        "organizacion",
        "usuario",
        "emergencia",
        "lote",
        "convocatoria",
        "convocatoria_lote",
        "oferta",
        "oferta_version",
        "oferta_item",
        "oferta_participante",
        "notificacion",
    }


def test_persiste_el_flujo_basico_con_defaults_y_relaciones(
    db_session: Session,
) -> None:
    municipio = _crear_organizacion(
        db_session,
        TipoOrganizacion.MUNICIPIO,
        "Municipio del Delta",
    )
    centro = _crear_organizacion(
        db_session,
        TipoOrganizacion.CENTRO_COORDINADOR,
        "Centro Litoral",
    )
    ong = _crear_organizacion(db_session, TipoOrganizacion.ONG, "Rescate Unido")
    operador = _crear_usuario(
        db_session,
        municipio,
        RolUsuario.OPERADOR_MUNICIPAL,
        "operador@delta.test",
    )
    coordinador = _crear_usuario(
        db_session,
        centro,
        RolUsuario.COORDINADOR_REGIONAL,
        "coordinador@litoral.test",
    )
    representante = _crear_usuario(
        db_session,
        ong,
        RolUsuario.REPRESENTANTE_ONG,
        "representante@rescate.test",
    )
    emergencia = _crear_emergencia(
        db_session,
        municipio,
        operador,
        "Ribera norte",
        centro,
    )
    lote = _crear_lote(db_session, emergencia, coordinador, "Alimentos")
    convocatoria = _crear_convocatoria(db_session, emergencia, 1)
    publicacion = _publicar_lote(db_session, convocatoria, lote)
    oferta, version = _crear_oferta(
        db_session,
        convocatoria,
        ong,
        representante,
    )
    item = OfertaItem(
        oferta_version_id=version.id,
        convocatoria_id=convocatoria.id,
        lote_id=lote.id,
        tipo=TipoAporte.RECURSO,
        descripcion="Raciones no perecederas",
        cantidad_ofrecida=Decimal(600),
        unidad="raciones",
    )
    participante = OfertaParticipante(
        oferta_id=oferta.id,
        ong_id=ong.id,
        rol=TipoParticipacion.LIDER,
    )
    db_session.add_all([item, participante])
    db_session.flush()

    assert emergencia.estado is EstadoEmergencia.REGISTRADA
    assert emergencia.bonita_sync is EstadoSincronizacionBonita.PENDIENTE
    assert lote.estado is EstadoLote.PUBLICADO
    assert convocatoria.estado is EstadoConvocatoria.ABIERTA
    assert publicacion.lote_id == lote.id
    assert item.convocatoria_lote == publicacion
    assert oferta.versiones == [version]
    assert oferta.participantes == [participante]
    assert emergencia.creada_en.tzinfo is not None


def test_email_es_unico_sin_distinguir_mayusculas(
    db_session: Session,
) -> None:
    ong = _crear_organizacion(db_session, TipoOrganizacion.ONG, "ONG Correo")
    _crear_usuario(
        db_session,
        ong,
        RolUsuario.REPRESENTANTE_ONG,
        "Ayuda@ong.test",
    )

    repetido = Usuario(
        organizacion_id=ong.id,
        email="ayuda@ONG.test",
        password_hash=ARGON2_HASH,
        rol=RolUsuario.REPRESENTANTE_ONG,
    )
    db_session.add(repetido)

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "uq_usuario_email_normalizado")


def test_rol_de_usuario_debe_corresponder_a_su_organizacion(
    db_session: Session,
) -> None:
    municipio = _crear_organizacion(
        db_session,
        TipoOrganizacion.MUNICIPIO,
        "Municipio incompatible",
    )
    usuario = Usuario(
        organizacion_id=municipio.id,
        email="ong@municipio.test",
        password_hash=ARGON2_HASH,
        rol=RolUsuario.REPRESENTANTE_ONG,
    )
    db_session.add(usuario)

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "ck_usuario_rol_organizacion")


def test_administrador_no_admite_organizacion(db_session: Session) -> None:
    municipio = _crear_organizacion(
        db_session,
        TipoOrganizacion.MUNICIPIO,
        "Municipio administrador inválido",
    )
    usuario = Usuario(
        organizacion_id=municipio.id,
        email="admin-organizacion@rescuesync.org",
        password_hash=ARGON2_HASH,
        rol=RolUsuario.ADMINISTRADOR,
    )
    db_session.add(usuario)

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "ck_usuario_rol_organizacion")


def test_version_de_sesion_debe_ser_positiva(db_session: Session) -> None:
    usuario = Usuario(
        organizacion_id=None,
        email="version-invalida@rescuesync.org",
        password_hash=ARGON2_HASH,
        rol=RolUsuario.AUDITOR_DIRECTIVO,
        version_sesion=0,
    )
    db_session.add(usuario)

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "ck_usuario_version_sesion_positiva")


def test_emergencia_requiere_una_organizacion_municipal(
    db_session: Session,
) -> None:
    ong = _crear_organizacion(db_session, TipoOrganizacion.ONG, "ONG no municipal")
    representante = _crear_usuario(
        db_session,
        ong,
        RolUsuario.REPRESENTANTE_ONG,
        "emergencia@ong.test",
    )
    emergencia = Emergencia(
        municipio_id=ong.id,
        creada_por_usuario_id=representante.id,
        gravedad=GravedadEmergencia.MEDIA,
        zona="Zona inválida",
        descripcion="Una ONG no puede ser el municipio afectado",
    )
    db_session.add(emergencia)

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "ck_emergencia_municipio_tipo")


def test_instancia_bonita_no_puede_vincularse_a_dos_emergencias(
    db_session: Session,
) -> None:
    municipio = _crear_organizacion(
        db_session,
        TipoOrganizacion.MUNICIPIO,
        "Municipio Bonita",
    )
    operador = _crear_usuario(
        db_session,
        municipio,
        RolUsuario.OPERADOR_MUNICIPAL,
        "bonita@municipio.test",
    )
    primera = _crear_emergencia(db_session, municipio, operador, "Zona Bonita uno")
    primera.bonita_process_instance_id = 987654
    primera.bonita_sync = EstadoSincronizacionBonita.VINCULADA
    db_session.flush()
    segunda = _crear_emergencia(db_session, municipio, operador, "Zona Bonita dos")
    segunda.bonita_process_instance_id = 987654
    segunda.bonita_sync = EstadoSincronizacionBonita.VINCULADA

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "uq_emergencia_bonita_process_instance_id")


def test_lote_rechaza_cantidades_no_positivas(db_session: Session) -> None:
    municipio = _crear_organizacion(
        db_session,
        TipoOrganizacion.MUNICIPIO,
        "Municipio Cantidades",
    )
    operador = _crear_usuario(
        db_session,
        municipio,
        RolUsuario.OPERADOR_MUNICIPAL,
        "cantidades@municipio.test",
    )
    emergencia = _crear_emergencia(
        db_session,
        municipio,
        operador,
        "Zona cantidades",
    )
    lote = Lote(
        emergencia_id=emergencia.id,
        creado_por_usuario_id=operador.id,
        tipo_necesidad="Agua",
        cantidad_requerida=Decimal(0),
        unidad="litros",
    )
    db_session.add(lote)

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "ck_lote_cantidad_positiva")


def test_emergencia_solo_acepta_una_convocatoria_abierta(
    db_session: Session,
) -> None:
    municipio = _crear_organizacion(
        db_session,
        TipoOrganizacion.MUNICIPIO,
        "Municipio Convocatoria",
    )
    operador = _crear_usuario(
        db_session,
        municipio,
        RolUsuario.OPERADOR_MUNICIPAL,
        "convocatoria@municipio.test",
    )
    emergencia = _crear_emergencia(
        db_session,
        municipio,
        operador,
        "Zona convocatoria",
    )
    _crear_convocatoria(db_session, emergencia, 1)
    segunda = Convocatoria(
        emergencia_id=emergencia.id,
        numero=2,
        publicada_en=datetime.now(UTC),
        cierra_en=datetime.now(UTC) + timedelta(hours=2),
    )
    db_session.add(segunda)

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "uq_convocatoria_abierta_por_emergencia")


def test_convocatoria_rechaza_lote_de_otra_emergencia(
    db_session: Session,
) -> None:
    municipio = _crear_organizacion(
        db_session,
        TipoOrganizacion.MUNICIPIO,
        "Municipio Lotes Cruzados",
    )
    operador = _crear_usuario(
        db_session,
        municipio,
        RolUsuario.OPERADOR_MUNICIPAL,
        "lotes-cruzados@municipio.test",
    )
    primera = _crear_emergencia(db_session, municipio, operador, "Zona uno")
    segunda = _crear_emergencia(db_session, municipio, operador, "Zona dos")
    lote_ajeno = _crear_lote(db_session, segunda, operador, "Medicamentos")
    convocatoria = _crear_convocatoria(db_session, primera, 1)
    publicacion_invalida = ConvocatoriaLote(
        convocatoria_id=convocatoria.id,
        lote_id=lote_ajeno.id,
        cantidad_publicada=Decimal(10),
        unidad_publicada="cajas",
    )
    db_session.add(publicacion_invalida)

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "ck_convocatoria_lote_misma_emergencia")


def test_item_rechaza_convocatoria_distinta_a_la_oferta(
    db_session: Session,
) -> None:
    municipio = _crear_organizacion(
        db_session,
        TipoOrganizacion.MUNICIPIO,
        "Municipio Ítems Cruzados",
    )
    ong = _crear_organizacion(db_session, TipoOrganizacion.ONG, "ONG Ítems Cruzados")
    operador = _crear_usuario(
        db_session,
        municipio,
        RolUsuario.OPERADOR_MUNICIPAL,
        "items@municipio.test",
    )
    representante = _crear_usuario(
        db_session,
        ong,
        RolUsuario.REPRESENTANTE_ONG,
        "items@ong.test",
    )
    emergencia = _crear_emergencia(db_session, municipio, operador, "Zona ítems")
    primer_lote = _crear_lote(db_session, emergencia, operador, "Agua")
    segundo_lote = _crear_lote(db_session, emergencia, operador, "Abrigo")
    primera = _crear_convocatoria(
        db_session,
        emergencia,
        1,
        EstadoConvocatoria.CERRADA,
    )
    segunda = _crear_convocatoria(db_session, emergencia, 2)
    _publicar_lote(db_session, primera, primer_lote)
    _publicar_lote(db_session, segunda, segundo_lote)
    _, version = _crear_oferta(db_session, primera, ong, representante)
    item_invalido = OfertaItem(
        oferta_version_id=version.id,
        convocatoria_id=segunda.id,
        lote_id=segundo_lote.id,
        tipo=TipoAporte.RECURSO,
        descripcion="Mantas térmicas",
        cantidad_ofrecida=Decimal(50),
        unidad="unidades",
    )
    db_session.add(item_invalido)

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "ck_oferta_item_misma_convocatoria")


def test_item_rechaza_lote_asociado_que_no_esta_publicado(
    db_session: Session,
) -> None:
    municipio = _crear_organizacion(
        db_session, TipoOrganizacion.MUNICIPIO, "Municipio Lote Borrador"
    )
    ong = _crear_organizacion(db_session, TipoOrganizacion.ONG, "ONG Lote Borrador")
    operador = _crear_usuario(
        db_session,
        municipio,
        RolUsuario.OPERADOR_MUNICIPAL,
        "borrador@municipio.test",
    )
    representante = _crear_usuario(
        db_session,
        ong,
        RolUsuario.REPRESENTANTE_ONG,
        "borrador@ong.test",
    )
    emergencia = _crear_emergencia(db_session, municipio, operador, "Zona borrador")
    lote = _crear_lote(db_session, emergencia, operador, "Agua")
    convocatoria = _crear_convocatoria(db_session, emergencia, 1)
    db_session.add(
        ConvocatoriaLote(
            convocatoria_id=convocatoria.id,
            lote_id=lote.id,
            cantidad_publicada=lote.cantidad_requerida,
            unidad_publicada=lote.unidad,
        )
    )
    db_session.flush()
    _, version = _crear_oferta(db_session, convocatoria, ong, representante)
    db_session.add(
        OfertaItem(
            oferta_version_id=version.id,
            convocatoria_id=convocatoria.id,
            lote_id=lote.id,
            tipo=TipoAporte.RECURSO,
            descripcion="Agua potable",
            cantidad_ofrecida=Decimal(10),
            unidad=lote.unidad,
        )
    )

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "ck_oferta_item_lote_publicado")


def test_oferta_es_unica_por_ong_y_convocatoria(db_session: Session) -> None:
    municipio = _crear_organizacion(
        db_session, TipoOrganizacion.MUNICIPIO, "Municipio Oferta Única"
    )
    ong = _crear_organizacion(db_session, TipoOrganizacion.ONG, "ONG Oferta Única")
    operador = _crear_usuario(
        db_session,
        municipio,
        RolUsuario.OPERADOR_MUNICIPAL,
        "oferta-unica@municipio.test",
    )
    representante = _crear_usuario(
        db_session,
        ong,
        RolUsuario.REPRESENTANTE_ONG,
        "oferta-unica@ong.test",
    )
    emergencia = _crear_emergencia(db_session, municipio, operador, "Zona oferta única")
    convocatoria = _crear_convocatoria(db_session, emergencia, 1)
    _crear_oferta(db_session, convocatoria, ong, representante)
    db_session.add(
        Oferta(
            convocatoria_id=convocatoria.id,
            ong_creadora_id=ong.id,
            creada_por_usuario_id=representante.id,
            estado=EstadoOferta.PRESENTADA,
        )
    )

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "uq_oferta_convocatoria_ong_vigente")


def test_item_rechaza_cantidad_mayor_que_la_publicada(
    db_session: Session,
) -> None:
    municipio = _crear_organizacion(
        db_session, TipoOrganizacion.MUNICIPIO, "Municipio Cantidad Máxima"
    )
    ong = _crear_organizacion(db_session, TipoOrganizacion.ONG, "ONG Cantidad Máxima")
    operador = _crear_usuario(
        db_session,
        municipio,
        RolUsuario.OPERADOR_MUNICIPAL,
        "cantidad-maxima@municipio.test",
    )
    representante = _crear_usuario(
        db_session,
        ong,
        RolUsuario.REPRESENTANTE_ONG,
        "cantidad-maxima@ong.test",
    )
    emergencia = _crear_emergencia(
        db_session, municipio, operador, "Zona cantidad máxima"
    )
    lote = _crear_lote(db_session, emergencia, operador, "Agua")
    convocatoria = _crear_convocatoria(db_session, emergencia, 1)
    _publicar_lote(db_session, convocatoria, lote)
    _, version = _crear_oferta(db_session, convocatoria, ong, representante)
    db_session.add(
        OfertaItem(
            oferta_version_id=version.id,
            convocatoria_id=convocatoria.id,
            lote_id=lote.id,
            tipo=TipoAporte.RECURSO,
            descripcion="Agua potable",
            cantidad_ofrecida=Decimal(1001),
            unidad=lote.unidad,
        )
    )

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "ck_oferta_item_cantidad_publicada")


def test_oferta_requiere_una_organizacion_ong(db_session: Session) -> None:
    municipio = _crear_organizacion(
        db_session,
        TipoOrganizacion.MUNICIPIO,
        "Municipio Ofertante Inválido",
    )
    operador = _crear_usuario(
        db_session,
        municipio,
        RolUsuario.OPERADOR_MUNICIPAL,
        "oferta-invalida@municipio.test",
    )
    emergencia = _crear_emergencia(
        db_session,
        municipio,
        operador,
        "Zona oferta inválida",
    )
    convocatoria = _crear_convocatoria(db_session, emergencia, 1)
    oferta = Oferta(
        convocatoria_id=convocatoria.id,
        ong_creadora_id=municipio.id,
        creada_por_usuario_id=operador.id,
    )
    db_session.add(oferta)

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "ck_oferta_ong_creadora_tipo")


def test_participante_de_oferta_debe_ser_una_ong(db_session: Session) -> None:
    municipio = _crear_organizacion(
        db_session,
        TipoOrganizacion.MUNICIPIO,
        "Municipio Participante Inválido",
    )
    ong = _crear_organizacion(
        db_session,
        TipoOrganizacion.ONG,
        "ONG con participante inválido",
    )
    operador = _crear_usuario(
        db_session,
        municipio,
        RolUsuario.OPERADOR_MUNICIPAL,
        "participante@municipio.test",
    )
    representante = _crear_usuario(
        db_session,
        ong,
        RolUsuario.REPRESENTANTE_ONG,
        "participante@ong.test",
    )
    emergencia = _crear_emergencia(
        db_session,
        municipio,
        operador,
        "Zona participante inválido",
    )
    convocatoria = _crear_convocatoria(db_session, emergencia, 1)
    oferta, _ = _crear_oferta(db_session, convocatoria, ong, representante)
    participante = OfertaParticipante(
        oferta_id=oferta.id,
        ong_id=municipio.id,
        rol=TipoParticipacion.MIEMBRO,
    )
    db_session.add(participante)

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "ck_oferta_participante_ong_tipo")


def test_oferta_conjunta_solo_acepta_una_ong_lider(
    db_session: Session,
) -> None:
    municipio = _crear_organizacion(
        db_session,
        TipoOrganizacion.MUNICIPIO,
        "Municipio Consorcios",
    )
    primera_ong = _crear_organizacion(
        db_session,
        TipoOrganizacion.ONG,
        "ONG Líder Uno",
    )
    segunda_ong = _crear_organizacion(
        db_session,
        TipoOrganizacion.ONG,
        "ONG Líder Dos",
    )
    operador = _crear_usuario(
        db_session,
        municipio,
        RolUsuario.OPERADOR_MUNICIPAL,
        "consorcios@municipio.test",
    )
    representante = _crear_usuario(
        db_session,
        primera_ong,
        RolUsuario.REPRESENTANTE_ONG,
        "consorcios@ong.test",
    )
    emergencia = _crear_emergencia(
        db_session,
        municipio,
        operador,
        "Zona consorcios",
    )
    convocatoria = _crear_convocatoria(db_session, emergencia, 1)
    oferta, _ = _crear_oferta(
        db_session,
        convocatoria,
        primera_ong,
        representante,
    )
    primer_lider = OfertaParticipante(
        oferta_id=oferta.id,
        ong_id=primera_ong.id,
        rol=TipoParticipacion.LIDER,
    )
    db_session.add(primer_lider)
    db_session.flush()
    segundo_lider = OfertaParticipante(
        oferta_id=oferta.id,
        ong_id=segunda_ong.id,
        rol=TipoParticipacion.LIDER,
    )
    db_session.add(segundo_lider)

    with pytest.raises(IntegrityError) as error:
        db_session.flush()

    _assert_restriccion(error, "uq_oferta_participante_lider")
