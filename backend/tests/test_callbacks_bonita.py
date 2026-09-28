from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
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
    Notificacion,
    Oferta,
    OfertaItem,
    OfertaVersion,
    Organizacion,
    RolUsuario,
    TipoAporte,
    TipoNotificacion,
    TipoOrganizacion,
    Usuario,
)
from app.db.session import get_db
from app.integrations.bonita.contratos import CABECERA_CASO_RAIZ
from app.main import app

TOKEN = "token-de-callbacks-de-prueba-con-32-caracteres"
CASE_ID = 4242
ARGON2_HASH = "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA"


@dataclass(frozen=True)
class Escenario:
    emergencia: Emergencia
    convocatoria: Convocatoria
    lote_agua: Lote
    lote_kits: Lote
    ong: Organizacion
    representante: Usuario


@pytest.fixture(autouse=True)
def token_configurado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "bonita_callback_token", SecretStr(TOKEN))


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def usar_sesion_de_prueba() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = usar_sesion_de_prueba
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _organizacion(
    session: Session, tipo: TipoOrganizacion, nombre: str
) -> Organizacion:
    organizacion = Organizacion(tipo=tipo, nombre=nombre)
    session.add(organizacion)
    session.flush()
    return organizacion


def _usuario(
    session: Session, organizacion: Organizacion, rol: RolUsuario, email: str
) -> Usuario:
    usuario = Usuario(
        organizacion_id=organizacion.id,
        email=email,
        password_hash=ARGON2_HASH,
        rol=rol,
    )
    session.add(usuario)
    session.flush()
    return usuario


@pytest.fixture
def escenario(db_session: Session) -> Escenario:
    ahora = datetime.now(UTC)
    municipio = _organizacion(db_session, TipoOrganizacion.MUNICIPIO, "Municipio CB")
    ong = _organizacion(db_session, TipoOrganizacion.ONG, "ONG CB")
    operador = _usuario(
        db_session, municipio, RolUsuario.OPERADOR_MUNICIPAL, "op@cb.org"
    )
    representante = _usuario(
        db_session, ong, RolUsuario.REPRESENTANTE_ONG, "ong@cb.org"
    )
    emergencia = Emergencia(
        municipio_id=municipio.id,
        creada_por_usuario_id=operador.id,
        gravedad=GravedadEmergencia.CRITICA,
        zona="Zona CB",
        descripcion="Emergencia para callbacks",
        bonita_process_instance_id=CASE_ID,
        bonita_sync=EstadoSincronizacionBonita.VINCULADA,
    )
    db_session.add(emergencia)
    db_session.flush()
    lotes = []
    for tipo, cantidad, unidad in (
        ("Agua", Decimal(1000), "litros"),
        ("Kits", Decimal(10), "kits"),
    ):
        lote = Lote(
            emergencia_id=emergencia.id,
            creado_por_usuario_id=operador.id,
            tipo_necesidad=tipo,
            cantidad_requerida=cantidad,
            unidad=unidad,
            estado=EstadoLote.PUBLICADO,
        )
        db_session.add(lote)
        lotes.append(lote)
    db_session.flush()
    convocatoria = Convocatoria(
        emergencia_id=emergencia.id,
        numero=1,
        publicada_en=ahora - timedelta(minutes=5),
        cierra_en=ahora + timedelta(days=1),
    )
    db_session.add(convocatoria)
    db_session.flush()
    for lote in lotes:
        db_session.add(
            ConvocatoriaLote(
                convocatoria_id=convocatoria.id,
                lote_id=lote.id,
                cantidad_publicada=lote.cantidad_requerida,
                unidad_publicada=lote.unidad,
            )
        )
    db_session.flush()
    return Escenario(emergencia, convocatoria, lotes[0], lotes[1], ong, representante)


def _oferta(
    session: Session,
    escenario: Escenario,
    estado: EstadoOferta,
    versiones: list[list[tuple[Lote, Decimal, str]]],
    presentada: bool = True,
) -> Oferta:
    oferta = Oferta(
        convocatoria_id=escenario.convocatoria.id,
        ong_creadora_id=escenario.ong.id,
        creada_por_usuario_id=escenario.representante.id,
        estado=estado,
        version_actual=len(versiones),
    )
    session.add(oferta)
    session.flush()
    for numero, items in enumerate(versiones, start=1):
        version = OfertaVersion(
            oferta_id=oferta.id,
            creada_por_usuario_id=escenario.representante.id,
            numero=numero,
            presentada_en=datetime.now(UTC) if presentada else None,
        )
        session.add(version)
        session.flush()
        for lote, cantidad, unidad in items:
            session.add(
                OfertaItem(
                    oferta_version_id=version.id,
                    convocatoria_id=escenario.convocatoria.id,
                    lote_id=lote.id,
                    tipo=TipoAporte.RECURSO,
                    descripcion=f"Aporte {lote.tipo_necesidad}",
                    cantidad_ofrecida=cantidad,
                    unidad=unidad,
                )
            )
    session.flush()
    return oferta


def _headers(token: str = TOKEN, case_id: int = CASE_ID) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", CABECERA_CASO_RAIZ: str(case_id)}


def _notificar(
    client: TestClient,
    escenario: Escenario,
    *,
    cierre: datetime,
    intento: int = 1,
    headers: dict[str, str] | None = None,
) -> object:
    emergencia_id = escenario.emergencia.id
    return client.post(
        f"/api/v1/emergencias/{emergencia_id}/notificar-apertura",
        json={
            "idEmergencia": emergencia_id,
            "intentoConvocatoria": intento,
            "fechaCierreOfertas": cierre.isoformat().replace("+00:00", "Z"),
        },
        headers=_headers() if headers is None else headers,
    )


def _cerrar(client: TestClient, escenario: Escenario, intento: int = 1) -> object:
    emergencia_id = escenario.emergencia.id
    return client.post(
        f"/api/v1/emergencias/{emergencia_id}/cerrar-convocatoria",
        json={"idEmergencia": emergencia_id, "intentoConvocatoria": intento},
        headers=_headers(),
    )


def _consolidadas(client: TestClient, escenario: Escenario) -> object:
    return client.get(
        f"/api/v1/emergencias/{escenario.emergencia.id}/ofertas-consolidadas",
        headers=_headers(),
    )


@pytest.mark.parametrize(
    "authorization",
    [None, "Bearer token-incorrecto-con-mas-de-32-caracteres", f"Basic {TOKEN}"],
)
def test_rechaza_callbacks_sin_token_valido_antes_de_validar_el_cuerpo(
    client: TestClient,
    escenario: Escenario,
    authorization: str | None,
) -> None:
    headers = {CABECERA_CASO_RAIZ: str(CASE_ID)}
    if authorization is not None:
        headers["Authorization"] = authorization

    response = client.post(
        f"/api/v1/emergencias/{escenario.emergencia.id}/notificar-apertura",
        json={"cuerpo": "invalido"},
        headers=headers,
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_responde_503_si_el_token_no_esta_configurado(
    client: TestClient,
    escenario: Escenario,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "bonita_callback_token", None)

    response = _consolidadas(client, escenario)

    assert response.status_code == 503


def test_notificacion_alinea_el_cierre_con_bonita_y_es_idempotente(
    client: TestClient,
    escenario: Escenario,
    db_session: Session,
) -> None:
    cierre = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=2)

    primera = _notificar(client, escenario, cierre=cierre)
    segunda = _notificar(client, escenario, cierre=cierre)

    assert primera.status_code == segunda.status_code == 200
    assert primera.json()["estado"] == "ABIERTA"
    assert primera.json()["convocatoriaId"] == escenario.convocatoria.id
    db_session.refresh(escenario.convocatoria)
    assert escenario.convocatoria.cierra_en == cierre
    avisos = db_session.scalars(
        select(Notificacion).where(
            Notificacion.usuario_id == escenario.representante.id,
            Notificacion.tipo == TipoNotificacion.CONVOCATORIA_ACTUALIZADA,
        )
    ).all()
    assert len(avisos) == 1


@pytest.mark.parametrize(
    ("cambios", "codigo"),
    [
        ({"case_id": CASE_ID + 1}, 409),
        ({"intento": 2}, 409),
        ({"cierre_en_pasado": True}, 422),
    ],
)
def test_notificacion_rechaza_datos_inconsistentes(
    client: TestClient,
    escenario: Escenario,
    cambios: dict[str, object],
    codigo: int,
) -> None:
    cierre = datetime.now(UTC) + timedelta(hours=2)
    if cambios.get("cierre_en_pasado"):
        cierre = escenario.convocatoria.publicada_en - timedelta(minutes=1)
    headers = _headers(case_id=int(cambios.get("case_id", CASE_ID)))

    response = _notificar(
        client,
        escenario,
        cierre=cierre,
        intento=int(cambios.get("intento", 1)),
        headers=headers,
    )

    assert response.status_code == codigo


def test_notificacion_rechaza_emergencia_inexistente_o_distinta_al_cuerpo(
    client: TestClient,
    escenario: Escenario,
) -> None:
    cuerpo = {
        "idEmergencia": escenario.emergencia.id,
        "intentoConvocatoria": 1,
        "fechaCierreOfertas": "2099-01-01T00:00:00Z",
    }

    inexistente = client.post(
        "/api/v1/emergencias/999999999/notificar-apertura",
        json=cuerpo | {"idEmergencia": 999999999},
        headers=_headers(),
    )
    distinta = client.post(
        f"/api/v1/emergencias/{escenario.emergencia.id + 1}/notificar-apertura",
        json=cuerpo,
        headers=_headers(),
    )
    sin_caso = client.post(
        f"/api/v1/emergencias/{escenario.emergencia.id}/notificar-apertura",
        json=cuerpo,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )

    assert inexistente.status_code == 404
    assert distinta.status_code == 422
    assert sin_caso.status_code == 422


def test_cierre_es_idempotente_y_bloquea_nuevas_notificaciones(
    client: TestClient,
    escenario: Escenario,
    db_session: Session,
) -> None:
    primera = _cerrar(client, escenario)
    segunda = _cerrar(client, escenario)

    assert primera.status_code == segunda.status_code == 200
    assert primera.json()["estado"] == "CERRADA"
    assert primera.json()["cerradaEn"] == segunda.json()["cerradaEn"]
    db_session.refresh(escenario.convocatoria)
    db_session.refresh(escenario.emergencia)
    assert escenario.convocatoria.estado is EstadoConvocatoria.CERRADA
    assert escenario.emergencia.estado is EstadoEmergencia.EN_EVALUACION
    aviso_municipal = db_session.scalar(
        select(Notificacion).where(
            Notificacion.usuario_id == escenario.emergencia.creada_por_usuario_id,
            Notificacion.tipo == TipoNotificacion.EMERGENCIA_ESTADO_ACTUALIZADO,
        )
    )
    assert aviso_municipal is not None
    reapertura = _notificar(
        client, escenario, cierre=datetime.now(UTC) + timedelta(hours=1)
    )
    assert reapertura.status_code == 409


def test_no_consolida_una_convocatoria_abierta(
    client: TestClient,
    escenario: Escenario,
) -> None:
    response = _consolidadas(client, escenario)

    assert response.status_code == 409


def test_consolida_solo_versiones_vigentes_presentadas_y_en_la_unidad_publicada(
    client: TestClient,
    escenario: Escenario,
    db_session: Session,
) -> None:
    agua, kits = escenario.lote_agua, escenario.lote_kits
    vigente = _oferta(
        db_session,
        escenario,
        EstadoOferta.PRESENTADA,
        [
            [(agua, Decimal(5000), "litros")],
            [(agua, Decimal(600), " Litros "), (kits, Decimal(4), "kits")],
        ],
    )
    _oferta(
        db_session,
        escenario,
        EstadoOferta.PRESENTADA,
        [[(agua, Decimal(400), "litros"), (kits, Decimal(99), "cajas")]],
    )
    _oferta(
        db_session, escenario, EstadoOferta.BORRADOR, [[(kits, Decimal(10), "kits")]]
    )
    _oferta(
        db_session, escenario, EstadoOferta.RETIRADA, [[(kits, Decimal(10), "kits")]]
    )
    _cerrar(client, escenario)

    response = _consolidadas(client, escenario)

    assert response.status_code == 200
    payload = response.json()
    assert payload["lotesCubiertos"] is False
    assert [len(oferta["items"]) for oferta in payload["ofertas"]] == [2, 2]
    assert payload["ofertas"][0]["ofertaId"] == vigente.id
    assert payload["ofertas"][0]["version"] == 2
    assert {lote["tipoNecesidad"]: lote for lote in payload["lotes"]} == {
        "Agua": {
            "loteId": agua.id,
            "tipoNecesidad": "Agua",
            "cantidadPublicada": 1000.0,
            "unidad": "litros",
            "cantidadOfrecida": 1000.0,
            "cubierto": True,
        },
        "Kits": {
            "loteId": kits.id,
            "tipoNecesidad": "Kits",
            "cantidadPublicada": 10.0,
            "unidad": "kits",
            "cantidadOfrecida": 4.0,
            "cubierto": False,
        },
    }


def test_consolidado_marca_lotes_cubiertos_cuando_todos_alcanzan(
    client: TestClient,
    escenario: Escenario,
    db_session: Session,
) -> None:
    _oferta(
        db_session,
        escenario,
        EstadoOferta.PRESENTADA,
        [
            [
                (escenario.lote_agua, Decimal(1000), "litros"),
                (escenario.lote_kits, Decimal(10), "kits"),
            ]
        ],
    )
    _cerrar(client, escenario)

    response = _consolidadas(client, escenario)

    assert response.status_code == 200
    assert response.json()["lotesCubiertos"] is True
