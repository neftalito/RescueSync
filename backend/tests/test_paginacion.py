from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import crear_valor_sesion, generar_password_hash
from app.db.models import (
    Emergencia,
    EstadoEmergencia,
    GravedadEmergencia,
    Lote,
    Notificacion,
    Organizacion,
    RolUsuario,
    TipoNotificacion,
    TipoOrganizacion,
    Usuario,
)
from app.db.session import get_db
from app.main import app


@dataclass
class EscenarioPaginacion:
    usuarios: dict[RolUsuario, Usuario]
    emergencias: list[Emergencia]


@pytest.fixture
def escenario(db_session: Session) -> EscenarioPaginacion:
    """Crea filas con fechas empatadas y datos ajenos para comprobar orden y alcance."""
    municipio = Organizacion(
        tipo=TipoOrganizacion.MUNICIPIO, nombre="Municipio paginado"
    )
    centro = Organizacion(
        tipo=TipoOrganizacion.CENTRO_COORDINADOR, nombre="Centro paginado"
    )
    ong = Organizacion(tipo=TipoOrganizacion.ONG, nombre="ONG paginada")
    otro = Organizacion(tipo=TipoOrganizacion.MUNICIPIO, nombre="Municipio ajeno")
    db_session.add_all([municipio, centro, ong, otro])
    db_session.flush()
    password_hash = generar_password_hash("Prueba-paginacion-2026")
    organizaciones = {
        RolUsuario.OPERADOR_MUNICIPAL: municipio.id,
        RolUsuario.COORDINADOR_REGIONAL: centro.id,
        RolUsuario.REPRESENTANTE_ONG: ong.id,
        RolUsuario.ADMINISTRADOR: None,
    }
    usuarios = {
        rol: Usuario(
            rol=rol,
            organizacion_id=organizacion_id,
            email=f"pagina-{rol.value.lower()}@example.org",
            password_hash=password_hash,
        )
        for rol, organizacion_id in organizaciones.items()
    }
    db_session.add_all(usuarios.values())
    db_session.flush()
    operador = usuarios[RolUsuario.OPERADOR_MUNICIPAL]
    coordinador = usuarios[RolUsuario.COORDINADOR_REGIONAL]
    emergencias = [
        Emergencia(
            municipio_id=municipio.id,
            centro_coordinador_id=centro.id,
            creada_por_usuario_id=operador.id,
            gravedad=GravedadEmergencia.ALTA,
            zona=f"Zona {indice}",
            descripcion="Emergencia de prueba",
            estado=EstadoEmergencia.REGISTRADA
            if indice < 4
            else EstadoEmergencia.PUBLICADA,
        )
        for indice in range(7)
    ]
    db_session.add_all(emergencias)
    db_session.add(
        Emergencia(
            municipio_id=otro.id,
            creada_por_usuario_id=operador.id,
            gravedad=GravedadEmergencia.ALTA,
            zona="Ajena",
            descripcion="No debe aparecer en la bandeja propia",
            estado=EstadoEmergencia.CANCELADA,
        )
    )
    db_session.flush()
    db_session.add_all(
        [
            Lote(
                emergencia_id=emergencia.id,
                creado_por_usuario_id=coordinador.id,
                tipo_necesidad="Agua",
                cantidad_requerida=Decimal(10),
                unidad="litros",
            )
            for indice, emergencia in enumerate(emergencias)
            if indice % 2 == 1 or indice >= 4
        ]
    )
    db_session.flush()
    return EscenarioPaginacion(usuarios, emergencias)


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def usar_sesion() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = usar_sesion
    try:
        with TestClient(app) as cliente:
            yield cliente
    finally:
        app.dependency_overrides.clear()


def autenticar(client: TestClient, usuario: Usuario) -> None:
    client.cookies.set(
        "rescuesync_session", crear_valor_sesion(usuario.id), path="/api/v1"
    )


@pytest.mark.parametrize(
    ("ruta", "rol"),
    [
        ("/usuarios", RolUsuario.ADMINISTRADOR),
        ("/organizaciones", RolUsuario.ADMINISTRADOR),
        ("/emergencias", RolUsuario.OPERADOR_MUNICIPAL),
        ("/emergencias/{id}/lotes", RolUsuario.COORDINADOR_REGIONAL),
        ("/convocatorias", RolUsuario.REPRESENTANTE_ONG),
        ("/ofertas", RolUsuario.REPRESENTANTE_ONG),
        ("/notificaciones", RolUsuario.OPERADOR_MUNICIPAL),
    ],
)
def test_rechaza_ventanas_invalidas_en_todos_los_listados(
    client: TestClient,
    escenario: EscenarioPaginacion,
    ruta: str,
    rol: RolUsuario,
) -> None:
    autenticar(client, escenario.usuarios[rol])
    url = "/api/v1" + ruta.format(id=escenario.emergencias[0].id)
    for parametros in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert client.get(url, params=parametros).status_code == 422


def test_pagina_solo_las_emergencias_propias_sin_repetir_fechas_empatadas(
    client: TestClient,
    escenario: EscenarioPaginacion,
) -> None:
    autenticar(client, escenario.usuarios[RolUsuario.OPERADOR_MUNICIPAL])
    esperados = [emergencia.id for emergencia in reversed(escenario.emergencias)]
    ids = []
    for offset in range(0, 9, 2):
        respuesta = client.get(
            "/api/v1/emergencias", params={"limit": 2, "offset": offset}
        )
        assert respuesta.status_code == 200
        ids.extend(item["id"] for item in respuesta.json())
    assert ids == esperados
    assert [
        item["id"] for item in client.get("/api/v1/emergencias").json()
    ] == esperados


def test_aplica_estado_y_existencia_de_lotes_antes_de_paginar(
    client: TestClient,
    escenario: EscenarioPaginacion,
) -> None:
    autenticar(client, escenario.usuarios[RolUsuario.COORDINADOR_REGIONAL])
    respuesta = client.get(
        "/api/v1/emergencias",
        params={
            "limit": 1,
            "offset": 1,
            "tiene_lotes": "true",
            "estado": "REGISTRADA",
        },
    )
    assert respuesta.status_code == 200
    assert [item["id"] for item in respuesta.json()] == [escenario.emergencias[3].id]
    assert respuesta.json()[0]["tiene_lotes"] is True


def test_busca_emergencias_antes_de_paginar_y_respeta_el_alcance(
    client: TestClient, db_session: Session, escenario: EscenarioPaginacion
) -> None:
    objetivo = escenario.emergencias[3]
    objetivo.descripcion = "Inundación con 50% de cobertura"
    escenario.emergencias[5].descripcion = "Inundacio\u0301n con 50% de cobertura"
    db_session.flush()

    autenticar(client, escenario.usuarios[RolUsuario.COORDINADOR_REGIONAL])
    respuesta = client.get(
        "/api/v1/emergencias",
        params={
            "q": " INUNDACION ",
            "tiene_lotes": True,
            "estado": "REGISTRADA",
            "limit": 1,
        },
    )
    assert respuesta.status_code == 200
    assert [fila["id"] for fila in respuesta.json()] == [objetivo.id]

    autenticar(client, escenario.usuarios[RolUsuario.OPERADOR_MUNICIPAL])
    for termino in ("%", "inundacion"):
        assert len(client.get("/api/v1/emergencias", params={"q": termino}).json()) == 2
    por_id = client.get("/api/v1/emergencias", params={"q": f"#{objetivo.id}"}).json()
    assert [fila["id"] for fila in por_id] == [objetivo.id]
    assert (
        client.get("/api/v1/emergencias", params={"q": "no debe aparecer"}).json() == []
    )
    assert client.get("/api/v1/emergencias", params={"q": "x" * 121}).status_code == 422


def test_busca_usuarios_por_correo_y_organizacion_con_filtros(
    client: TestClient, db_session: Session, escenario: EscenarioPaginacion
) -> None:
    objetivo = escenario.usuarios[RolUsuario.REPRESENTANTE_ONG]
    assert objetivo.organizacion is not None
    objetivo.organizacion.nombre = "Asociación del valle"
    objetivo.activo = False
    db_session.flush()
    autenticar(client, escenario.usuarios[RolUsuario.ADMINISTRADOR])

    for termino in ("ASOCIACION", objetivo.email.upper()):
        respuesta = client.get(
            "/api/v1/usuarios",
            params={
                "q": termino,
                "rol": objetivo.rol.value,
                "activo": False,
                "limit": 1,
            },
        )
        assert respuesta.status_code == 200
        assert [fila["id"] for fila in respuesta.json()] == [objetivo.id]
    assert (
        client.get(
            "/api/v1/usuarios", params={"q": "asociacion", "activo": True}
        ).json()
        == []
    )


def test_busca_organizaciones_por_nombre_con_filtros(
    client: TestClient, db_session: Session, escenario: EscenarioPaginacion
) -> None:
    objetivo = escenario.usuarios[RolUsuario.REPRESENTANTE_ONG].organizacion
    assert objetivo is not None
    objetivo.nombre = "Fundación del valle"
    objetivo.activa = False
    db_session.flush()
    autenticar(client, escenario.usuarios[RolUsuario.ADMINISTRADOR])

    respuesta = client.get(
        "/api/v1/organizaciones",
        params={"q": "FUNDACION", "tipo": "ONG", "activa": False, "limit": 1},
    )
    assert respuesta.status_code == 200
    assert [fila["id"] for fila in respuesta.json()] == [objetivo.id]
    assert (
        client.get(
            "/api/v1/organizaciones", params={"q": "fundacion", "tipo": "MUNICIPIO"}
        ).json()
        == []
    )


@pytest.mark.parametrize("ruta", ["usuarios", "organizaciones"])
def test_paginas_de_administracion_conservan_el_orden_del_listado_completo(
    client: TestClient,
    escenario: EscenarioPaginacion,
    ruta: str,
) -> None:
    autenticar(client, escenario.usuarios[RolUsuario.ADMINISTRADOR])
    completos = client.get(f"/api/v1/{ruta}").json()
    assert len(completos) >= 4
    pagina = client.get(f"/api/v1/{ruta}", params={"limit": 2, "offset": 2})
    assert pagina.status_code == 200
    assert pagina.json() == completos[2:4]


def test_permite_recuperar_notificaciones_anteriores_a_las_ultimas_cincuenta(
    client: TestClient,
    db_session: Session,
    escenario: EscenarioPaginacion,
) -> None:
    propio = escenario.usuarios[RolUsuario.OPERADOR_MUNICIPAL]
    ajeno = escenario.usuarios[RolUsuario.REPRESENTANTE_ONG]
    notificaciones = [
        Notificacion(
            usuario_id=propio.id,
            clave_evento=f"paginacion:{indice}",
            tipo=TipoNotificacion.EMERGENCIA_ESTADO_ACTUALIZADO,
            titulo=f"Novedad {indice}",
            mensaje="Novedad propia",
        )
        for indice in range(55)
    ]
    db_session.add_all(notificaciones)
    db_session.add(
        Notificacion(
            usuario_id=ajeno.id,
            clave_evento="paginacion:ajena",
            tipo=TipoNotificacion.CONVOCATORIA_PUBLICADA,
            titulo="Ajena",
            mensaje="No debe aparecer",
        )
    )
    db_session.flush()
    autenticar(client, propio)
    assert len(client.get("/api/v1/notificaciones").json()) == 50
    respuesta = client.get("/api/v1/notificaciones", params={"limit": 20, "offset": 40})
    assert respuesta.status_code == 200
    assert [item["id"] for item in respuesta.json()] == [
        notificacion.id for notificacion in reversed(notificaciones[:15])
    ]
