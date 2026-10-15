"""Obtiene tokens por ONG sin confirmar transacciones del caso de uso llamador."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    AccesoNacional,
    Organizacion,
    RolUsuario,
    TipoOrganizacion,
    Usuario,
)
from app.integrations.nacional.cliente import ClienteNacional, ErrorNacional
from app.schemas.inventario import ConexionRequest, CredencialTecnica
from app.services.auth import usuario_tiene_contexto_vigente

logger = logging.getLogger(__name__)


def cifrador() -> Fernet:
    clave = get_settings().nacional_encryption_key
    if clave is None:
        raise ErrorNacional(
            503, "El acceso nacional requiere configuración administrativa."
        )
    return Fernet(clave.get_secret_value().encode())


def _ong(usuario: Usuario) -> Organizacion:
    ong = usuario.organizacion
    if (
        not usuario_tiene_contexto_vigente(usuario)
        or usuario.requiere_cambio_password
        or usuario.rol != RolUsuario.REPRESENTANTE_ONG
        or ong is None
        or ong.tipo != TipoOrganizacion.ONG
    ):
        raise ErrorNacional(
            403, "Necesitás una cuenta representante y una ONG local activas."
        )
    if ong.ong_nacional_id is None:
        raise ErrorNacional(
            409, "Un administrador debe vincular tu ONG al Sistema Nacional."
        )
    return ong


def importar_credencial(
    session: Session,
    organizacion_id: int,
    datos: CredencialTecnica,
    cliente: ClienteNacional,
) -> None:
    """Verifica pertenencia remota antes de bloquear y reemplazar la configuración."""
    cifrado = cifrador().encrypt(datos.password.get_secret_value().encode()).decode()
    token = cliente.login(
        ConexionRequest(
            identificador_login=datos.identificador_login, password=datos.password
        )
    )
    cuenta = cliente.cuenta(token.access_token.get_secret_value())
    if (
        cuenta.rol != "ONG"
        or cuenta.proposito != "TECNICA_ONG"
        or cuenta.ong_id != datos.ong_id
        or cuenta.id != datos.cuenta_id
    ):
        raise ErrorNacional(
            403, "El archivo no corresponde a una cuenta técnica de esa ONG."
        )
    ong = session.scalar(
        select(Organizacion).where(Organizacion.id == organizacion_id).with_for_update()
    )
    if (
        ong is None
        or not ong.activa
        or ong.tipo != TipoOrganizacion.ONG
        or ong.ong_nacional_id != datos.ong_id
    ):
        raise ErrorNacional(
            409,
            "La ONG local debe estar activa y vinculada al UUID nacional del archivo.",
        )
    acceso = session.get(AccesoNacional, organizacion_id)
    if acceso is None:
        acceso = AccesoNacional(organizacion_id=organizacion_id)
        session.add(acceso)
    acceso.ong_id = datos.ong_id
    acceso.cuenta_id = datos.cuenta_id
    acceso.configuracion_id = uuid4()
    acceso.identificador_login = datos.identificador_login
    acceso.secreto_cifrado = cifrado
    acceso.token_cifrado = None
    acceso.expira_en = None
    acceso.requiere_revision = False
    session.flush()


def _guardar(
    session: Session,
    acceso: AccesoNacional,
    *,
    token: str | None = None,
    expira_en: datetime | None = None,
    revision: bool = False,
    token_esperado: str | None = None,
) -> None:
    """Actualiza sólo la configuración usada; no pisa una importación concurrente."""
    with Session(
        bind=session.get_bind(), join_transaction_mode="create_savepoint"
    ) as db:
        consulta = update(AccesoNacional).where(
            AccesoNacional.organizacion_id == acceso.organizacion_id,
            AccesoNacional.configuracion_id == acceso.configuracion_id,
        )
        if token_esperado is not None:
            consulta = consulta.where(AccesoNacional.token_cifrado == token_esperado)
        resultado = db.execute(
            consulta.values(
                token_cifrado=cifrador().encrypt(token.encode()).decode()
                if token
                else None,
                expira_en=expira_en,
                requiere_revision=revision,
            )
        )
        if resultado.rowcount != 1:
            raise ErrorNacional(
                409, "La configuración nacional cambió. Volvé a intentar."
            )
        db.commit()


def credencial(
    session: Session,
    usuario: Usuario,
    cliente: ClienteNacional,
    *,
    renovar: bool = False,
) -> tuple[UUID, str]:
    """Lee la configuración compartida y autentica sin mantener locks durante HTTP."""
    ong = _ong(usuario)
    assert ong.ong_nacional_id is not None
    with Session(
        bind=session.get_bind(),
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    ) as db:
        acceso = db.get(AccesoNacional, ong.id)
    if acceso is None or acceso.ong_id != ong.ong_nacional_id:
        raise ErrorNacional(
            503, "Un administrador debe configurar el acceso nacional de tu ONG."
        )
    if acceso.requiere_revision:
        raise ErrorNacional(
            503, "El acceso nacional de tu ONG requiere revisión administrativa."
        )
    try:
        fernet = cifrador()
        if (
            not renovar
            and acceso.token_cifrado
            and acceso.expira_en
            and acceso.expira_en > datetime.now(UTC) + timedelta(seconds=30)
        ):
            return acceso.ong_id, fernet.decrypt(acceso.token_cifrado.encode()).decode()
        secreto = fernet.decrypt(acceso.secreto_cifrado.encode()).decode()
    except InvalidToken as error:
        _guardar(session, acceso, revision=True)
        raise ErrorNacional(
            503, "El acceso nacional requiere reimportar la credencial institucional."
        ) from error
    inicio = datetime.now(UTC)
    try:
        respuesta = cliente.login(
            ConexionRequest(
                identificador_login=acceso.identificador_login, password=secreto
            )
        )
        token = respuesta.access_token.get_secret_value()
        cuenta = cliente.cuenta(token)
        if (
            cuenta.id != acceso.cuenta_id
            or cuenta.rol != "ONG"
            or cuenta.proposito != "TECNICA_ONG"
            or cuenta.ong_id != acceso.ong_id
        ):
            raise ErrorNacional(
                403, "La identidad técnica no corresponde a la ONG vinculada."
            )
    except ErrorNacional as error:
        if error.status in {401, 403}:
            _guardar(session, acceso, revision=True)
            raise ErrorNacional(
                503, "El acceso nacional de tu ONG requiere revisión administrativa."
            ) from error
        raise
    _guardar(
        session,
        acceso,
        token=token,
        expira_en=inicio + timedelta(seconds=respuesta.expires_in),
    )
    return acceso.ong_id, token


def ejecutar_nacional[T](
    session: Session,
    usuario: Usuario,
    cliente: ClienteNacional,
    operacion: Callable[[UUID, str], T],
    *,
    escritura: bool = False,
    accion: str = "consultar referencias",
) -> T:
    """Renueva una sola vez ante 401 y reintenta únicamente consultas."""
    ong_id, token = credencial(session, usuario, cliente)
    try:
        resultado = operacion(ong_id, token)
    except ErrorNacional as error:
        if error.status != 401:
            raise
        ong_id, token = credencial(session, usuario, cliente, renovar=True)
        if escritura:
            raise ErrorNacional(
                409,
                "Se renovó el acceso nacional. Revisá el resultado antes de repetir la operación.",
            ) from error
        try:
            resultado = operacion(ong_id, token)
        except ErrorNacional as nuevo_error:
            if nuevo_error.status == 401:
                with Session(
                    bind=session.get_bind(), join_transaction_mode="create_savepoint"
                ) as db:
                    acceso = db.get(AccesoNacional, usuario.organizacion_id)
                # Un rechazo atrasado no invalida el token nuevo de otro worker.
                if (
                    acceso is not None
                    and acceso.token_cifrado is not None
                    and cifrador().decrypt(acceso.token_cifrado.encode()).decode()
                    == token
                ):
                    _guardar(
                        session,
                        acceso,
                        revision=True,
                        token_esperado=acceso.token_cifrado,
                    )
                raise ErrorNacional(
                    503, "El acceso nacional requiere revisión administrativa."
                ) from nuevo_error
            raise
    logger.info(
        "Operación nacional completada usuario_id=%s ong_id=%s escritura=%s accion=%s",
        usuario.id,
        ong_id,
        escritura,
        accion,
    )
    return resultado
