"""Persistencia y consulta de novedades dirigidas a usuarios autenticados."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import (
    Notificacion,
    Organizacion,
    RolUsuario,
    TipoNotificacion,
    Usuario,
)
from app.schemas.paginacion import SIN_PAGINACION, Paginacion

LIMITE_NOTIFICACIONES = 50


class NotificacionNoEncontradaError(Exception):
    """La notificación no existe o pertenece a otro usuario."""


def clave_emergencia_registrada(emergencia_id: int) -> str:
    return f"emergencia:{emergencia_id}:registrada"


def clave_convocatoria_publicada(convocatoria_id: int) -> str:
    return f"convocatoria:{convocatoria_id}:publicada"


def clave_convocatoria_cerrada(convocatoria_id: int) -> str:
    return f"convocatoria:{convocatoria_id}:cerrada"


def clave_oferta_recibida(oferta_id: int) -> str:
    return f"oferta:{oferta_id}:recibida"


def notificar_emergencia_registrada(
    session: Session,
    *,
    emergencia_id: int,
    zona: str,
) -> None:
    """Avisa a coordinadores activos que una emergencia requiere lotes."""

    _crear_para_rol(
        session,
        rol=RolUsuario.COORDINADOR_REGIONAL,
        clave_evento=clave_emergencia_registrada(emergencia_id),
        tipo=TipoNotificacion.EMERGENCIA_REGISTRADA,
        titulo="Nueva emergencia pendiente",
        mensaje=f"Se registró una emergencia en {zona} que requiere lotes.",
        ruta=f"/emergencias/{emergencia_id}/lotes",
    )


def notificar_tarea_bonita_fallida(
    session: Session, *, tarea_id: int, emergencia_id: int, nombre: str
) -> list[Notificacion]:
    """Persiste una alerta por auditor y tarea sin duplicarla entre sondeos o workers."""
    auditores = session.scalars(
        select(Usuario.id).where(
            Usuario.rol == RolUsuario.AUDITOR_DIRECTIVO, Usuario.activo.is_(True)
        )
    ).all()
    if not auditores:
        return []
    notificaciones = list(
        session.scalars(
            insert(Notificacion)
            .values(
                [
                    {
                        "usuario_id": usuario_id,
                        "clave_evento": f"bonita:tarea:{tarea_id}:fallida",
                        "tipo": TipoNotificacion.TAREA_BONITA_FALLIDA,
                        "titulo": "Tarea de Bonita con errores",
                        "mensaje": f"La tarea {nombre[:160] or 'sin nombre'} de la emergencia #{emergencia_id} está fallida y requiere revisión.",
                        "ruta": "/",
                        "emergencia_id": emergencia_id,
                        "tarea_bonita_nombre": nombre[:160] or "Sin nombre",
                    }
                    for usuario_id in auditores
                ]
            )
            .on_conflict_do_nothing(constraint="uq_notificacion_usuario_evento")
            .returning(Notificacion)
        ).all()
    )
    for notificacion in notificaciones:
        notificacion.ruta = f"/notificaciones/{notificacion.id}"
    return notificaciones


def notificar_convocatoria_publicada(
    session: Session,
    *,
    convocatoria_id: int,
    emergencia_id: int,
    municipio_id: int,
    zona: str,
    descripcion: str,
) -> None:
    """Avisa a las ONGs de la apertura y al municipio del cambio de estado."""

    clave = clave_convocatoria_publicada(convocatoria_id)
    _crear_para_rol(
        session,
        rol=RolUsuario.REPRESENTANTE_ONG,
        clave_evento=clave,
        tipo=TipoNotificacion.CONVOCATORIA_PUBLICADA,
        titulo="Nueva convocatoria abierta",
        mensaje=f"Se publicó una convocatoria para la emergencia de {zona}.",
        ruta=None,
    )
    _crear_para_organizacion(
        session,
        organizacion_id=municipio_id,
        rol=RolUsuario.OPERADOR_MUNICIPAL,
        clave_evento=clave,
        tipo=TipoNotificacion.EMERGENCIA_ESTADO_ACTUALIZADO,
        titulo="Emergencia publicada",
        mensaje=(
            "El centro coordinador publicó la convocatoria de la emergencia en "
            f"{zona}: {descripcion}"
        ),
        ruta=f"/emergencias/{emergencia_id}/ejecucion",
    )


def notificar_convocatoria_cerrada(
    session: Session,
    *,
    convocatoria_id: int,
    emergencia_id: int,
    municipio_id: int,
    zona: str,
    descripcion: str,
) -> None:
    """Comunica el cierre a ONGs y el paso a evaluación al municipio."""

    clave = clave_convocatoria_cerrada(convocatoria_id)
    _crear_para_rol(
        session,
        rol=RolUsuario.REPRESENTANTE_ONG,
        clave_evento=clave,
        tipo=TipoNotificacion.CONVOCATORIA_CERRADA,
        titulo="Convocatoria cerrada",
        mensaje=f"Finalizó la recepción de ofertas para la emergencia de {zona}.",
        ruta=None,
    )
    _crear_para_organizacion(
        session,
        organizacion_id=municipio_id,
        rol=RolUsuario.OPERADOR_MUNICIPAL,
        clave_evento=clave,
        tipo=TipoNotificacion.EMERGENCIA_ESTADO_ACTUALIZADO,
        titulo="Emergencia en evaluación",
        mensaje=(
            "Cerró la convocatoria y las ofertas están siendo evaluadas. "
            f"Emergencia en {zona}: {descripcion}"
        ),
        ruta=f"/emergencias/{emergencia_id}/ejecucion",
    )


def notificar_oferta_recibida(
    session: Session,
    *,
    oferta_id: int,
    centro_coordinador_id: int | None,
    zona: str,
) -> None:
    """Avisa al centro asignado que una ONG presentó una oferta."""

    if centro_coordinador_id is None:
        return
    _crear_para_organizacion(
        session,
        organizacion_id=centro_coordinador_id,
        rol=RolUsuario.COORDINADOR_REGIONAL,
        clave_evento=clave_oferta_recibida(oferta_id),
        tipo=TipoNotificacion.OFERTA_RECIBIDA,
        titulo="Nueva oferta recibida",
        mensaje=f"Una ONG presentó una oferta para la emergencia de {zona}.",
        ruta=None,
    )


def listar_notificaciones(
    session: Session,
    usuario: Usuario,
    paginacion: Paginacion = SIN_PAGINACION,
) -> list[Notificacion]:
    """Devuelve las últimas novedades del usuario sin exponer otros buzones."""

    return list(
        session.scalars(
            select(Notificacion)
            .where(Notificacion.usuario_id == usuario.id)
            .order_by(Notificacion.creada_en.desc(), Notificacion.id.desc())
            .offset(paginacion.offset)
            .limit(paginacion.limit or LIMITE_NOTIFICACIONES)
        ).all()
    )


def listar_por_clave(session: Session, clave_evento: str) -> list[Notificacion]:
    """Obtiene el abanico persistido que debe emitirse después del commit."""

    return list(
        session.scalars(
            select(Notificacion)
            .where(Notificacion.clave_evento == clave_evento)
            .order_by(Notificacion.id)
        ).all()
    )


def marcar_como_leida(
    session: Session,
    usuario: Usuario,
    notificacion_id: int,
) -> Notificacion:
    """Marca una novedad propia como leída de forma idempotente."""

    notificacion = session.scalar(
        select(Notificacion)
        .where(
            Notificacion.id == notificacion_id,
            Notificacion.usuario_id == usuario.id,
        )
        .with_for_update()
    )
    if notificacion is None:
        raise NotificacionNoEncontradaError("La notificación no existe.")
    if notificacion.leida_en is None:
        notificacion.leida_en = datetime.now(UTC)
        session.commit()
        session.refresh(notificacion)
    return notificacion


def marcar_todas_como_leidas(
    session: Session, usuario: Usuario
) -> tuple[int, datetime]:
    """Marca en una sola operación todas las novedades pendientes del usuario."""

    leida_en = datetime.now(UTC)
    ids_actualizados = session.scalars(
        update(Notificacion)
        .where(
            Notificacion.usuario_id == usuario.id,
            Notificacion.leida_en.is_(None),
        )
        .values(leida_en=leida_en)
        .returning(Notificacion.id)
    ).all()
    session.commit()
    return len(ids_actualizados), leida_en


def _crear_para_rol(
    session: Session,
    *,
    rol: RolUsuario,
    clave_evento: str,
    tipo: TipoNotificacion,
    titulo: str,
    mensaje: str,
    ruta: str | None,
) -> None:
    usuarios = session.scalars(
        select(Usuario)
        .join(Organizacion, Organizacion.id == Usuario.organizacion_id)
        .where(
            Usuario.rol == rol,
            Usuario.activo.is_(True),
            Organizacion.activa.is_(True),
        )
    ).all()
    _crear_para_usuarios(
        session,
        usuarios=usuarios,
        clave_evento=clave_evento,
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje,
        ruta=ruta,
    )


def _crear_para_organizacion(
    session: Session,
    *,
    organizacion_id: int,
    rol: RolUsuario,
    clave_evento: str,
    tipo: TipoNotificacion,
    titulo: str,
    mensaje: str,
    ruta: str | None,
) -> None:
    usuarios = session.scalars(
        select(Usuario)
        .join(Organizacion, Organizacion.id == Usuario.organizacion_id)
        .where(
            Usuario.organizacion_id == organizacion_id,
            Usuario.rol == rol,
            Usuario.activo.is_(True),
            Organizacion.activa.is_(True),
        )
    ).all()
    _crear_para_usuarios(
        session,
        usuarios=usuarios,
        clave_evento=clave_evento,
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje,
        ruta=ruta,
    )


def _crear_para_usuarios(
    session: Session,
    *,
    usuarios: list[Usuario],
    clave_evento: str,
    tipo: TipoNotificacion,
    titulo: str,
    mensaje: str,
    ruta: str | None,
) -> None:
    ids = [usuario.id for usuario in usuarios]
    if not ids:
        return
    existentes = set(
        session.scalars(
            select(Notificacion.usuario_id).where(
                Notificacion.usuario_id.in_(ids),
                Notificacion.clave_evento == clave_evento,
            )
        ).all()
    )
    nuevas = [
        Notificacion(
            usuario_id=usuario_id,
            clave_evento=clave_evento,
            tipo=tipo,
            titulo=titulo,
            mensaje=mensaje,
            ruta=ruta,
        )
        for usuario_id in ids
        if usuario_id not in existentes
    ]
    session.add_all(nuevas)
    if tipo in {
        TipoNotificacion.OFERTA_RECIBIDA,
        TipoNotificacion.CONVOCATORIA_PUBLICADA,
        TipoNotificacion.CONVOCATORIA_CERRADA,
    }:
        session.flush()
        for notificacion in nuevas:
            notificacion.ruta = f"/notificaciones/{notificacion.id}"
