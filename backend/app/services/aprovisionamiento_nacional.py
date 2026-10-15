"""Aprovisiona acceso automático sin mantener locks durante llamadas nacionales."""

from secrets import token_urlsafe
from uuid import uuid4

from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AccesoNacional, Organizacion, TipoOrganizacion
from app.db.models.aprovisionamiento import AprovisionamientoNacional
from app.integrations.nacional.cliente import ClienteNacional, ErrorNacional
from app.schemas.inventario import (
    AprovisionamientoRequest,
    ConexionRequest,
    RegistroNacionalRequest,
)
from app.services.acceso_nacional import cifrador


def preparar_alta(
    session: Session,
    ong: Organizacion,
    datos: RegistroNacionalRequest,
) -> None:
    """Persiste una referencia y secreto estables antes del primer envío."""
    ong = session.scalar(
        select(Organizacion)
        .where(Organizacion.id == ong.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        ong is None
        or not ong.activa
        or ong.tipo != TipoOrganizacion.ONG
        or ong.ong_nacional_id is not None
    ):
        raise ErrorNacional(409, "La ONG ya está vinculada o no está activa.")
    pendiente = session.get(AprovisionamientoNacional, ong.id)
    if pendiente is not None:
        if pendiente.email_contacto != (
            str(datos.email_contacto) if datos.email_contacto else None
        ):
            raise ErrorNacional(
                409, "El alta nacional ya está iniciada con otro correo de contacto."
            )
        return
    session.add(
        AprovisionamientoNacional(
            organizacion_id=ong.id,
            nombre=ong.nombre,
            email_contacto=(
                str(datos.email_contacto) if datos.email_contacto else None
            ),
            secreto_cifrado=cifrador().encrypt(token_urlsafe(32).encode()).decode(),
        )
    )
    session.flush()


def completar_alta(
    session: Session,
    organizacion_id: int,
    cliente: ClienteNacional,
) -> Organizacion:
    """Reutiliza la solicitud durable y confirma el vínculo y acceso juntos."""
    ong = session.get(Organizacion, organizacion_id, populate_existing=True)
    if ong is None or ong.tipo != TipoOrganizacion.ONG or not ong.activa:
        raise ErrorNacional(403, "Se requiere una ONG local activa.")
    if ong.ong_nacional_id is not None:
        acceso = session.get(AccesoNacional, ong.id, populate_existing=True)
        if acceso is None or acceso.ong_id != ong.ong_nacional_id:
            raise ErrorNacional(
                409, "La ONG anterior requiere importar su credencial institucional."
            )
        return ong
    pendiente = session.get(AprovisionamientoNacional, ong.id)
    if pendiente is None:
        preparar_alta(session, ong, RegistroNacionalRequest())
        session.commit()
        pendiente = session.get(AprovisionamientoNacional, organizacion_id)
        assert pendiente is not None
    referencia = pendiente.referencia
    secreto_cifrado = pendiente.secreto_cifrado
    try:
        secreto = cifrador().decrypt(secreto_cifrado.encode()).decode()
    except InvalidToken as error:
        raise ErrorNacional(
            503,
            "La clave de cifrado del alta nacional requiere revisión administrativa.",
        ) from error
    datos = AprovisionamientoRequest(
        nombre=pendiente.nombre,
        email_contacto=pendiente.email_contacto,
        password=secreto,
    )
    # Libera la transacción antes de salir a la red; preparar_alta ya fue confirmado.
    session.rollback()
    settings = get_settings()
    if (
        not settings.nacional_aprovisionamiento_login
        or settings.nacional_aprovisionamiento_password is None
    ):
        raise ErrorNacional(
            503, "El servicio de alta nacional requiere configuración administrativa."
        )
    token = cliente.login(
        ConexionRequest(
            identificador_login=settings.nacional_aprovisionamiento_login,
            password=settings.nacional_aprovisionamiento_password,
        )
    )
    resultado = cliente.aprovisionar_ong(
        token.access_token.get_secret_value(), referencia, datos
    )
    ong = session.scalar(
        select(Organizacion)
        .where(
            Organizacion.id == organizacion_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if ong is None or ong.tipo != TipoOrganizacion.ONG or not ong.activa:
        raise ErrorNacional(409, "La organización cambió durante el alta nacional.")
    vigente = session.get(
        AprovisionamientoNacional, organizacion_id, populate_existing=True
    )
    if (
        vigente is None
        or vigente.referencia != referencia
        or vigente.secreto_cifrado != secreto_cifrado
    ):
        raise ErrorNacional(409, "La configuración nacional cambió durante el alta.")
    if ong.ong_nacional_id not in {None, resultado.ong.id}:
        raise ErrorNacional(
            409, "La ONG tiene otra vinculación nacional; requiere revisión."
        )
    acceso = session.get(AccesoNacional, ong.id, populate_existing=True)
    if acceso is not None and acceso.ong_id != resultado.ong.id:
        raise ErrorNacional(409, "El acceso nacional cambió durante el alta.")
    if acceso is None:
        session.add(
            AccesoNacional(
                organizacion_id=ong.id,
                ong_id=resultado.ong.id,
                cuenta_id=resultado.cuenta_id,
                configuracion_id=uuid4(),
                identificador_login=resultado.identificador_login,
                secreto_cifrado=secreto_cifrado,
                requiere_revision=False,
            )
        )
    ong.ong_nacional_id = resultado.ong.id
    session.commit()
    return ong
