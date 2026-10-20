"""Captura real, consentimiento por versión, diagnóstico legacy y exactitud del GET."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import respx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import Connection, delete, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_ofertas import (
    ARGON2_HASH,
    Escenario,
    _autenticar_con_cookie,
    _usuario,
    client,
    escenario,
)

from app.core.config import get_settings
from app.db.models import (
    AccesoNacional,
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    EstadoOferta,
    EstadoSincronizacionBonita,
    GravedadEmergencia,
    Oferta,
    OfertaItemAporte,
    OfertaVersion,
    Organizacion,
    RolUsuario,
    TipoOrganizacion,
    Usuario,
)
from app.db.session import engine, get_db_consolidado
from app.main import app
from app.schemas.inventario import RecursoResponse
from app.schemas.oferta import OfertaCreateRequest, OfertaUpdateRequest
from app.services.acceso_nacional import cifrador
from app.services.callbacks_bonita import consolidar_ofertas
from app.services.consolidado_nacional import respuesta_consolidada
from app.services.consorcios import (
    confirmar_consorcio,
    desarmar_consorcio,
    proponer_consorcio,
)
from app.services.ofertas import (
    OfertaYaExisteError,
    VersionOfertaDesactualizadaError,
    actualizar_oferta,
    registrar_oferta,
)

__all__ = ["client", "escenario"]


@pytest.fixture
def capacidad(db_session: Session, escenario: Escenario) -> UUID:
    capacidad_id = uuid4()
    escenario.ong.ong_nacional_id = uuid4()
    escenario.otra_ong.ong_nacional_id = uuid4()
    escenario.convocatoria.sistema_origen_ref = "instalacion-prueba"
    escenario.convocatoria.gravedad_publicada = GravedadEmergencia.CRITICA
    publicacion = db_session.scalar(
        select(ConvocatoriaLote).where(
            ConvocatoriaLote.convocatoria_id == escenario.convocatoria.id,
            ConvocatoriaLote.lote_id == escenario.lote_agua.id,
        )
    )
    assert publicacion is not None
    publicacion.capacidad_nacional_id = capacidad_id
    publicacion.codigo_capacidad_publicada = "AGUA"
    publicacion.admite_fracciones_publicada = True
    publicacion.riesgo_requerido_publicado = GravedadEmergencia.ALTA
    # El otro lote no se oferta en estas pruebas, pero el consolidado lo diagnostica.
    db_session.commit()
    return capacidad_id


def recurso(
    usuario: Usuario, capacidad_id: UUID, recurso_id: UUID | None = None
) -> RecursoResponse:
    assert (
        usuario.organizacion is not None
        and usuario.organizacion.ong_nacional_id is not None
    )
    return RecursoResponse(
        id=recurso_id or uuid4(),
        ong_id=usuario.organizacion.ong_nacional_id,
        capacidad_id=capacidad_id,
        codigo_interno="AGUA",
        nombre="Agua propia",
        capacidad="Agua",
        unidad="litros",
        admite_fracciones=True,
        cantidad_total=Decimal(1000),
        cantidad_comprometida=Decimal(0),
        cantidad_disponible=Decimal(1000),
        activo=True,
        actualizado_en=datetime.now(UTC),
    )


def contenido(
    escenario: Escenario, recurso_id: UUID, cantidad: str
) -> OfertaCreateRequest:
    return OfertaCreateRequest.model_validate(
        {
            "convocatoria_id": escenario.convocatoria.id,
            "items": [
                {
                    "lote_id": escenario.lote_agua.id,
                    "tipo": "RECURSO",
                    "descripcion": "Agua propia",
                    "cantidad_ofrecida": cantidad,
                    "unidad": "litros",
                    "aportes": [
                        {"recurso_nacional_id": str(recurso_id), "cantidad": cantidad}
                    ],
                }
            ],
        }
    )


def presentar(
    db: Session,
    escenario: Escenario,
    usuario: Usuario,
    capacidad_id: UUID,
    cantidad: str = "300.125",
) -> Oferta:
    r = recurso(usuario, capacidad_id)
    return registrar_oferta(
        db,
        usuario,
        contenido(escenario, r.id, cantidad),
        referencias=(r.ong_id, {r.id: r}),
    )


def cerrar(db: Session, escenario: Escenario) -> None:
    escenario.convocatoria.estado = EstadoConvocatoria.CERRADA
    escenario.convocatoria.cerrada_en = datetime.now(UTC)
    db.commit()


def test_get_conserva_referencias_congeladas_y_cantidades_exactas(
    db_session: Session, escenario: Escenario, capacidad: UUID
) -> None:
    oferta = presentar(db_session, escenario, escenario.representante, capacidad)
    nacional_original = escenario.ong.ong_nacional_id
    escenario.ong.ong_nacional_id = uuid4()
    escenario.emergencia.gravedad = GravedadEmergencia.BAJA
    cerrar(db_session, escenario)
    snapshot = respuesta_consolidada(
        consolidar_ofertas(
            db_session, emergencia_id=escenario.emergencia.id, case_id=4242
        ),
        4242,
    ).model_dump(mode="json", by_alias=True)
    ofrecida = snapshot["ofertas"][0]
    assert ofrecida["ofertaId"] == oferta.id
    assert ofrecida["ongNacionalId"] == str(nacional_original)
    assert ofrecida["items"][0]["cantidadOfrecida"] == 300.125
    assert ofrecida["items"][0]["cantidadOfrecidaExacta"] == "300.125"
    assert ofrecida["items"][0]["aportes"][0]["cantidad"] == "300.125"
    assert ofrecida["referenciasNacionalesCompletas"] is True
    assert snapshot["gravedad"] == "CRITICA" and snapshot["caseId"] == "4242"
    assert snapshot["lotes"][0]["riesgoRequerido"] == "ALTA"
    assert snapshot["referenciasNacionalesCompletas"] is False


def test_consorcio_necesita_aceptacion_y_consolida_un_solo_snapshot(
    db_session: Session, escenario: Escenario, capacidad: UUID
) -> None:
    primera = presentar(
        db_session, escenario, escenario.representante, capacidad, "300.125"
    )
    miembro = _usuario(
        db_session,
        escenario.otra_ong,
        RolUsuario.REPRESENTANTE_ONG,
        "miembro-snapshot@example.test",
    )
    segunda = presentar(db_session, escenario, miembro, capacidad, "400.250")
    propuesta = proponer_consorcio(
        db_session,
        escenario.representante,
        primera.id,
        primera.version_bloqueo,
        [miembro.organizacion_id],
    )
    assert propuesta.estado == EstadoOferta.BORRADOR
    assert segunda.fusionada_en_oferta_id is None
    propuesta = confirmar_consorcio(
        db_session, miembro, propuesta.id, propuesta.version_bloqueo
    )
    assert propuesta.estado == EstadoOferta.PRESENTADA
    assert segunda.fusionada_en_oferta_id == propuesta.id
    cerrar(db_session, escenario)
    snapshot = respuesta_consolidada(
        consolidar_ofertas(
            db_session, emergencia_id=escenario.emergencia.id, case_id=4242
        ),
        4242,
    )
    assert len(snapshot.ofertas) == 1
    oferta = snapshot.ofertas[0]
    assert len(oferta.participantes) == 2 and len(oferta.items[0].aportes) == 2
    assert oferta.items[0].cantidad_ofrecida_exacta == Decimal("700.375")
    assert {a.ong_id for a in oferta.items[0].aportes} == {
        escenario.ong.id,
        escenario.otra_ong.id,
    }
    assert sum(a.cantidad for a in oferta.items[0].aportes) == Decimal("700.375")


def test_propuesta_vieja_no_toma_una_version_nueva_del_miembro(
    db_session: Session, escenario: Escenario, capacidad: UUID
) -> None:
    primera = presentar(db_session, escenario, escenario.representante, capacidad)
    miembro = _usuario(
        db_session,
        escenario.otra_ong,
        RolUsuario.REPRESENTANTE_ONG,
        "miembro-version@example.test",
    )
    segunda = presentar(db_session, escenario, miembro, capacidad)
    propuesta = proponer_consorcio(
        db_session,
        escenario.representante,
        primera.id,
        primera.version_bloqueo,
        [miembro.organizacion_id],
    )
    r = recurso(miembro, capacidad)
    datos = OfertaUpdateRequest(
        version_bloqueo=segunda.version_bloqueo,
        **contenido(escenario, r.id, "200").model_dump(exclude={"convocatoria_id"}),
    )
    actualizar_oferta(
        db_session, miembro, segunda.id, datos, referencias=(r.ong_id, {r.id: r})
    )
    with pytest.raises(VersionOfertaDesactualizadaError):
        confirmar_consorcio(
            db_session, miembro, propuesta.id, propuesta.version_bloqueo
        )
    db_session.rollback()
    restaurada = desarmar_consorcio(
        db_session, escenario.representante, primera.id, primera.version_bloqueo
    )
    assert restaurada.version_actual == 1
    r = recurso(escenario.representante, capacidad)
    siguiente = actualizar_oferta(
        db_session,
        escenario.representante,
        primera.id,
        OfertaUpdateRequest(
            version_bloqueo=restaurada.version_bloqueo,
            **contenido(escenario, r.id, "250").model_dump(exclude={"convocatoria_id"}),
        ),
        referencias=(r.ong_id, {r.id: r}),
    )
    assert siguiente.version_actual == 3


def test_mapping_faltante_no_se_inventa_al_consolidar(
    client: TestClient,
    db_session: Session,
    escenario: Escenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_callbacks_bonita import Escenario as EscenarioCallback
    from test_callbacks_bonita import _oferta

    callback = EscenarioCallback(
        escenario.emergencia,
        escenario.convocatoria,
        escenario.lote_agua,
        escenario.lote_kits,
        escenario.ong,
        escenario.representante,
    )
    _oferta(
        db_session,
        callback,
        EstadoOferta.PRESENTADA,
        [[(escenario.lote_agua, Decimal(1), "litros")]],
        identificador_ong="legacy",
    )
    cerrar(db_session, escenario)
    token = "callback-snapshot-prueba-de-32-caracteres"
    monkeypatch.setattr(get_settings(), "bonita_callback_token", SecretStr(token))

    def database() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db_consolidado] = database
    try:
        response = client.get(
            f"/api/v1/emergencias/{escenario.emergencia.id}/ofertas-consolidadas",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Bonita-Root-Process-Instance-Id": "4242",
            },
        )
        assert (
            response.status_code == 200
            and response.headers["cache-control"] == "no-store"
        )
        oferta = response.json()["ofertas"][0]
        assert (
            oferta["ongNacionalId"] is None
            and oferta["referenciasNacionalesCompletas"] is False
        )
        assert "DESGLOSE_NACIONAL_AUSENTE" in {
            m["codigo"] for m in oferta["motivosIntegracion"]
        }
        assert (
            client.get(
                f"/api/v1/emergencias/{escenario.emergencia.id}/ofertas-consolidadas?intentoConvocatoria=2",
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-Bonita-Root-Process-Instance-Id": "4242",
                },
            ).status_code
            == 409
        )
    finally:
        app.dependency_overrides.pop(get_db_consolidado, None)


def test_nueva_ronda_abierta_rechaza_consolidado_anterior(
    db_session: Session, escenario: Escenario, capacidad: UUID
) -> None:
    presentar(db_session, escenario, escenario.representante, capacidad)
    cerrar(db_session, escenario)
    ahora = datetime.now(UTC)
    db_session.add(
        Convocatoria(
            emergencia_id=escenario.emergencia.id,
            numero=2,
            estado=EstadoConvocatoria.ABIERTA,
            publicada_en=ahora,
            cierra_en=ahora + timedelta(hours=1),
        )
    )
    db_session.commit()
    from app.services.callbacks_bonita import EstadoConvocatoriaInvalidoError

    with pytest.raises(EstadoConvocatoriaInvalidoError):
        consolidar_ofertas(
            db_session, emergencia_id=escenario.emergencia.id, case_id=4242
        )


@pytest.mark.parametrize("tabla", ["aporte", "participante", "publicacion"])
def test_snapshots_presentados_son_inmutables_en_postgresql(
    db_session: Session, escenario: Escenario, capacidad: UUID, tabla: str
) -> None:
    oferta = presentar(db_session, escenario, escenario.representante, capacidad)
    version = next(v for v in oferta.versiones if v.numero == oferta.version_actual)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        if tabla == "aporte":
            version.items[0].aportes[0].cantidad = Decimal(1)
        elif tabla == "participante":
            version.participantes[0].ong_nacional_id = uuid4()
        else:
            publicacion = db_session.scalar(
                select(ConvocatoriaLote).where(
                    ConvocatoriaLote.convocatoria_id == escenario.convocatoria.id,
                    ConvocatoriaLote.lote_id == escenario.lote_agua.id,
                )
            )
            assert publicacion is not None
            publicacion.capacidad_nacional_id = uuid4()
        db_session.flush()


def test_completitud_diferida_y_pertenencia_se_validan_en_la_base(
    db_session: Session, escenario: Escenario, capacidad: UUID
) -> None:
    oferta = presentar(db_session, escenario, escenario.representante, capacidad)
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(
            OfertaVersion(
                oferta_id=oferta.id,
                numero=2,
                creada_por_usuario_id=escenario.representante.id,
                requiere_desglose_nacional=True,
                presentada_en=datetime.now(UTC),
            )
        )
        db_session.flush()
        db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    with pytest.raises(IntegrityError), db_session.begin_nested():
        version = OfertaVersion(
            oferta_id=oferta.id,
            numero=3,
            creada_por_usuario_id=escenario.representante.id,
            requiere_desglose_nacional=True,
        )
        db_session.add(version)
        db_session.flush()
        original = oferta.versiones[0].items[0]
        db_session.add(
            OfertaItemAporte(
                oferta_item_id=original.id,
                oferta_version_id=version.id,
                ong_id=escenario.ong.id,
                recurso_nacional_id=uuid4(),
                capacidad_nacional_id=capacidad,
                cantidad=Decimal(1),
                unidad="litros",
            )
        )
        db_session.flush()


def test_captura_http_verifica_dueño_sin_confiar_en_uuid_arbitrario(
    client: TestClient,
    db_session: Session,
    escenario: Escenario,
    capacidad: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usuario = escenario.representante
    csrf = _autenticar_con_cookie(client, usuario)
    assert (
        usuario.organizacion is not None
        and usuario.organizacion.ong_nacional_id is not None
    )
    ong_id = usuario.organizacion.ong_nacional_id
    monkeypatch.setattr(
        get_settings(),
        "nacional_encryption_key",
        SecretStr(Fernet.generate_key().decode()),
    )
    db_session.add(
        AccesoNacional(
            organizacion_id=usuario.organizacion_id,
            cuenta_id=uuid4(),
            configuracion_id=uuid4(),
            identificador_login="tecnica",
            secreto_cifrado=cifrador().encrypt(b"secreto-prueba").decode(),
            ong_id=ong_id,
            token_cifrado=cifrador().encrypt(b"jwt-prueba").decode(),
            expira_en=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    db_session.commit()
    r = recurso(usuario, capacidad)
    base = str(get_settings().nacional_base_url).rstrip("/")
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{base}/ongs/{ong_id}/recursos").respond(
            200, json=[r.model_dump(mode="json", by_alias=True)]
        )
        mock.get(f"{base}/capacidades").respond(
            200,
            json=[
                {
                    "id": str(capacidad),
                    "codigo": "AGUA",
                    "nombre": "Agua",
                    "tipo": "SUMINISTRO",
                    "unidad": "litros",
                    "admiteFracciones": True,
                }
            ],
        )
        response = client.post(
            "/api/v1/ofertas",
            headers={"X-CSRF-Token": csrf},
            json=contenido(escenario, uuid4(), "200").model_dump(mode="json"),
        )
        assert response.status_code == 422
        response = client.post(
            "/api/v1/ofertas",
            headers={"X-CSRF-Token": csrf},
            json=contenido(escenario, r.id, "200").model_dump(mode="json"),
        )
        assert response.status_code == 201
        assert response.json()["items"][0]["aportes"][0]["ong_id"] == escenario.ong.id
        assert all("jwt-prueba" not in str(call.request.content) for call in mock.calls)


def test_aportes_rechazan_sumas_duplicados_y_dueño_en_payload(
    escenario: Escenario,
) -> None:
    datos = contenido(escenario, uuid4(), "10").model_dump()
    datos["items"][0]["aportes"][0]["cantidad"] = Decimal(9)
    with pytest.raises(ValidationError):
        OfertaCreateRequest.model_validate(datos)
    datos = contenido(escenario, uuid4(), "10").model_dump()
    datos["items"][0]["aportes"][0]["ong_id"] = escenario.otra_ong.id
    with pytest.raises(ValidationError):
        OfertaCreateRequest.model_validate(datos)


def test_cancelar_otra_invitacion_no_deshace_un_consorcio_confirmado(
    db_session: Session, escenario: Escenario, capacidad: UUID
) -> None:
    lider = presentar(db_session, escenario, escenario.representante, capacidad)
    miembro = _usuario(
        db_session,
        escenario.otra_ong,
        RolUsuario.REPRESENTANTE_ONG,
        "miembro-doble@example.test",
    )
    fuente = presentar(db_session, escenario, miembro, capacidad)
    tercera = Organizacion(
        tipo=TipoOrganizacion.ONG, nombre="Tercera ONG", ong_nacional_id=uuid4()
    )
    db_session.add(tercera)
    db_session.flush()
    otro_lider = _usuario(
        db_session,
        tercera,
        RolUsuario.REPRESENTANTE_ONG,
        "otra-invitacion@example.test",
    )
    otra = presentar(db_session, escenario, otro_lider, capacidad, "100")
    conjunta = proponer_consorcio(
        db_session,
        escenario.representante,
        lider.id,
        lider.version_bloqueo,
        [escenario.otra_ong.id],
    )
    pendiente = proponer_consorcio(
        db_session, otro_lider, otra.id, otra.version_bloqueo, [escenario.otra_ong.id]
    )
    confirmar_consorcio(db_session, miembro, conjunta.id, conjunta.version_bloqueo)
    desarmar_consorcio(db_session, otro_lider, pendiente.id, pendiente.version_bloqueo)
    assert fuente.fusionada_en_oferta_id == conjunta.id
    r = recurso(miembro, capacidad)
    with pytest.raises(OfertaYaExisteError):
        registrar_oferta(
            db_session,
            miembro,
            contenido(escenario, r.id, "50"),
            referencias=(r.ong_id, {r.id: r}),
        )


def test_get_observa_un_snapshot_aunque_se_reabra_desde_otra_conexion() -> None:
    """Una ronda nueva entre consultas no cambia la ronda del snapshot ya abierto."""
    identificador = uuid4().hex
    with Session(engine, expire_on_commit=False) as preparacion:
        municipio = Organizacion(
            tipo=TipoOrganizacion.MUNICIPIO, nombre=f"Snapshot {identificador}"
        )
        preparacion.add(municipio)
        preparacion.flush()
        operador = Usuario(
            organizacion_id=municipio.id,
            rol=RolUsuario.OPERADOR_MUNICIPAL,
            email=f"snapshot-{identificador}@example.test",
            password_hash=ARGON2_HASH,
        )
        preparacion.add(operador)
        preparacion.flush()
        emergencia = Emergencia(
            municipio_id=municipio.id,
            creada_por_usuario_id=operador.id,
            gravedad=GravedadEmergencia.ALTA,
            zona="Snapshot",
            descripcion="Lectura concurrente",
            bonita_process_instance_id=4242,
            bonita_sync=EstadoSincronizacionBonita.VINCULADA,
        )
        preparacion.add(emergencia)
        preparacion.flush()
        ahora = datetime.now(UTC)
        preparacion.add(
            Convocatoria(
                emergencia_id=emergencia.id,
                numero=1,
                estado=EstadoConvocatoria.CERRADA,
                publicada_en=ahora - timedelta(hours=2),
                cierra_en=ahora - timedelta(hours=1),
                cerrada_en=ahora,
            )
        )
        preparacion.commit()
        emergencia_id, usuario_id, municipio_id = (
            emergencia.id,
            operador.id,
            municipio.id,
        )
    abierta = False

    def reabrir(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        nonlocal abierta
        if abierta or "FROM convocatoria" not in statement:
            return
        abierta = True
        with Session(engine) as escritura:
            ahora = datetime.now(UTC)
            escritura.add(
                Convocatoria(
                    emergencia_id=emergencia_id,
                    numero=2,
                    estado=EstadoConvocatoria.ABIERTA,
                    publicada_en=ahora,
                    cierra_en=ahora + timedelta(hours=1),
                )
            )
            escritura.commit()

    generador = get_db_consolidado()
    lectura = next(generador)
    bind = lectura.get_bind()
    event.listen(bind, "before_cursor_execute", reabrir)
    try:
        snapshot = consolidar_ofertas(
            lectura, emergencia_id=emergencia_id, case_id=4242
        )
        assert abierta and snapshot.convocatoria.numero == 1
    finally:
        event.remove(bind, "before_cursor_execute", reabrir)
        generador.close()
        with Session(engine) as limpieza:
            limpieza.execute(
                delete(Convocatoria).where(Convocatoria.emergencia_id == emergencia_id)
            )
            limpieza.execute(delete(Emergencia).where(Emergencia.id == emergencia_id))
            limpieza.execute(delete(Usuario).where(Usuario.id == usuario_id))
            limpieza.execute(
                delete(Organizacion).where(Organizacion.id == municipio_id)
            )
            limpieza.commit()
