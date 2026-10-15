import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generar_password_hash
from app.db.models import (
    AccesoNacional,
    Convocatoria,
    ConvocatoriaLote,
    Emergencia,
    EstadoConvocatoria,
    EstadoEmergencia,
    EstadoLote,
    EstadoOferta,
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
from app.db.session import SessionLocal
from app.services.acceso_nacional import cifrador
from app.services.bootstrap import asegurar_admin_inicial


@dataclass(frozen=True)
class CuentaSeed:
    email: str
    rol: RolUsuario
    organizacion: str | None


@dataclass(frozen=True)
class SeedResult:
    cuentas: tuple[CuentaSeed, ...]
    emergencias: int
    lotes_publicados: int
    ofertas: int


def _organizacion(
    session: Session,
    tipo: TipoOrganizacion,
    nombre: str,
) -> Organizacion:
    organizacion = session.scalar(
        select(Organizacion).where(
            Organizacion.tipo == tipo,
            Organizacion.nombre == nombre,
        )
    )
    if organizacion is None:
        organizacion = Organizacion(tipo=tipo, nombre=nombre)
        session.add(organizacion)
        session.flush()
    else:
        organizacion.activa = True
    return organizacion


def _usuario(
    session: Session,
    email: str,
    email_anterior: str,
    rol: RolUsuario,
    organizacion: Organizacion | None,
) -> Usuario:
    usuario = session.scalar(
        select(Usuario).where(func.lower(Usuario.email) == email.lower())
    )
    if usuario is None:
        usuario = session.scalar(
            select(Usuario).where(func.lower(Usuario.email) == email_anterior.lower())
        )
    if usuario is None:
        usuario = Usuario(email=email)
        session.add(usuario)

    usuario.email = email
    usuario.organizacion_id = organizacion.id if organizacion is not None else None
    usuario.rol = rol
    nombre_usuario, separador, _ = email.partition("@")
    if not separador or not nombre_usuario:
        raise ValueError("el correo del seed no tiene un formato válido")
    usuario.password_hash = generar_password_hash(f"{nombre_usuario.lower()}123")
    usuario.activo = True
    session.flush()
    return usuario


def _emergencia(
    session: Session,
    municipio: Organizacion,
    operador: Usuario,
    centro: Organizacion | None,
    gravedad: GravedadEmergencia,
    zona: str,
    descripcion: str,
    estado: EstadoEmergencia,
) -> Emergencia:
    emergencia = session.scalar(
        select(Emergencia).where(
            Emergencia.municipio_id == municipio.id,
            Emergencia.zona == zona,
        )
    )
    if emergencia is None:
        emergencia = Emergencia(
            municipio_id=municipio.id,
            creada_por_usuario_id=operador.id,
            gravedad=gravedad,
            zona=zona,
            descripcion=descripcion,
        )
        session.add(emergencia)

    emergencia.centro_coordinador_id = centro.id if centro is not None else None
    emergencia.gravedad = gravedad
    emergencia.descripcion = descripcion
    emergencia.estado = estado
    session.flush()
    return emergencia


def _lote(
    session: Session,
    emergencia: Emergencia,
    coordinador: Usuario,
    tipo_necesidad: str,
    descripcion: str,
    cantidad: Decimal,
    unidad: str,
) -> Lote:
    lote = session.scalar(
        select(Lote).where(
            Lote.emergencia_id == emergencia.id,
            Lote.tipo_necesidad == tipo_necesidad,
        )
    )
    if lote is None:
        lote = Lote(
            emergencia_id=emergencia.id,
            creado_por_usuario_id=coordinador.id,
            tipo_necesidad=tipo_necesidad,
            cantidad_requerida=cantidad,
            unidad=unidad,
        )
        session.add(lote)

    lote.descripcion = descripcion
    lote.cantidad_requerida = cantidad
    lote.unidad = unidad
    lote.estado = EstadoLote.PUBLICADO
    session.flush()
    return lote


def _convocatoria(
    session: Session,
    emergencia: Emergencia,
    lotes: tuple[Lote, ...],
    ahora: datetime,
) -> Convocatoria:
    convocatoria = session.scalar(
        select(Convocatoria).where(
            Convocatoria.emergencia_id == emergencia.id,
            Convocatoria.numero == 1,
        )
    )
    if convocatoria is None:
        convocatoria = Convocatoria(emergencia_id=emergencia.id, numero=1)
        session.add(convocatoria)

    convocatoria.estado = EstadoConvocatoria.ABIERTA
    convocatoria.publicada_en = ahora
    convocatoria.cierra_en = ahora + timedelta(days=2)
    convocatoria.cerrada_en = None
    session.flush()

    for lote in lotes:
        publicacion = session.get(ConvocatoriaLote, (convocatoria.id, lote.id))
        if publicacion is None:
            publicacion = ConvocatoriaLote(
                convocatoria_id=convocatoria.id,
                lote_id=lote.id,
                cantidad_publicada=lote.cantidad_requerida,
                unidad_publicada=lote.unidad,
            )
            session.add(publicacion)
        else:
            publicacion.cantidad_publicada = lote.cantidad_requerida
            publicacion.unidad_publicada = lote.unidad
    session.flush()
    return convocatoria


def _oferta(
    session: Session,
    convocatoria: Convocatoria,
    ong: Organizacion,
    representante: Usuario,
    lote_agua: Lote,
    lote_salud: Lote,
    ahora: datetime,
) -> Oferta:
    oferta = session.scalar(
        select(Oferta).where(
            Oferta.convocatoria_id == convocatoria.id,
            Oferta.ong_creadora_id == ong.id,
            Oferta.fusionada_en_oferta_id.is_(None),
        )
    )
    if oferta is None:
        oferta = Oferta(
            convocatoria_id=convocatoria.id,
            ong_creadora_id=ong.id,
            creada_por_usuario_id=representante.id,
        )
        session.add(oferta)

    oferta.estado = EstadoOferta.PRESENTADA
    oferta.version_actual = 1
    session.flush()

    version = session.scalar(
        select(OfertaVersion).where(
            OfertaVersion.oferta_id == oferta.id,
            OfertaVersion.numero == 1,
        )
    )
    if version is None:
        version = OfertaVersion(
            oferta_id=oferta.id,
            creada_por_usuario_id=representante.id,
            numero=1,
        )
        session.add(version)
    version.observaciones = "Oferta parcial de demostración para pruebas locales."
    version.presentada_en = ahora
    session.flush()

    aportes = (
        (
            lote_agua,
            TipoAporte.RECURSO,
            "Agua potable embotellada",
            Decimal(3000),
            "litros",
        ),
        (
            lote_salud,
            TipoAporte.MIXTO,
            "Kits de primeros auxilios con personal sanitario",
            Decimal(10),
            "kits",
        ),
    )
    for lote, tipo, descripcion, cantidad, unidad in aportes:
        item = session.scalar(
            select(OfertaItem).where(
                OfertaItem.oferta_version_id == version.id,
                OfertaItem.lote_id == lote.id,
            )
        )
        if item is None:
            item = OfertaItem(
                oferta_version_id=version.id,
                convocatoria_id=convocatoria.id,
                lote_id=lote.id,
                tipo=tipo,
                descripcion=descripcion,
                cantidad_ofrecida=cantidad,
                unidad=unidad,
            )
            session.add(item)
        else:
            item.tipo = tipo
            item.descripcion = descripcion
            item.cantidad_ofrecida = cantidad
            item.unidad = unidad

    participante = session.get(OfertaParticipante, (oferta.id, ong.id))
    if participante is None:
        session.add(
            OfertaParticipante(
                oferta_id=oferta.id,
                ong_id=ong.id,
                rol=TipoParticipacion.LIDER,
            )
        )
    else:
        participante.rol = TipoParticipacion.LIDER
    session.flush()
    return oferta


def _acceso_nacional_demo(session: Session, ong: Organizacion, referencia: str) -> None:
    """Prepara el secreto técnico del seed nacional sin pisar accesos importados."""
    acceso = session.get(AccesoNacional, ong.id)
    if acceso is not None:
        if acceso.ong_id != ong.ong_nacional_id:
            raise ValueError(
                "La ONG demo tiene acceso configurado para otro UUID nacional."
            )
        return
    assert ong.ong_nacional_id is not None
    # Las mismas referencias y credenciales demo se crean en RescueSyncAPI.
    secreto = f"demo-only-rescuesync-tecnica:{referencia}:2026"
    session.add(
        AccesoNacional(
            organizacion_id=ong.id,
            ong_id=ong.ong_nacional_id,
            cuenta_id=uuid5(
                NAMESPACE_URL, f"rescuesync-demo:cuenta-tecnica:{referencia}"
            ),
            configuracion_id=uuid4(),
            identificador_login=f"demo-tecnica-{referencia}",
            secreto_cifrado=cifrador().encrypt(secreto.encode()).decode(),
            requiere_revision=False,
        )
    )
    session.flush()


def seed_development_data(
    session: Session, *, incluir_dashboard: bool = True
) -> SeedResult:
    """Carga escenarios operativos y de auditoría reproducibles sin duplicarlos."""

    settings = get_settings()
    if settings.app_env.casefold() not in {"development", "test"}:
        raise ValueError("El seed sólo está disponible en desarrollo y pruebas.")
    if settings.nacional_encryption_key is None:
        raise ValueError(
            "Configurá NACIONAL_ENCRYPTION_KEY en el backend antes de ejecutar el seed."
        )
    administrador = asegurar_admin_inicial(session, settings)

    municipio = _organizacion(
        session,
        TipoOrganizacion.MUNICIPIO,
        "Municipalidad de Puerto Esperanza",
    )
    centro = _organizacion(
        session,
        TipoOrganizacion.CENTRO_COORDINADOR,
        "Centro Coordinador Litoral",
    )
    ong = _organizacion(session, TipoOrganizacion.ONG, "Ayuda Sin Fronteras")
    red_medica = _organizacion(session, TipoOrganizacion.ONG, "Red Médica Solidaria")
    for organizacion, referencia in (
        (ong, "ayuda-sin-fronteras"),
        (red_medica, "red-medica-solidaria"),
    ):
        ong_id = uuid5(NAMESPACE_URL, f"rescuesync-demo:ong:{referencia}")
        if organizacion.ong_nacional_id not in {None, ong_id}:
            raise ValueError("La ONG demo ya tiene otra vinculación nacional.")
        organizacion.ong_nacional_id = ong_id
        _acceso_nacional_demo(session, organizacion, referencia)

    operador = _usuario(
        session,
        "municipio@rescuesync.org",
        "municipio@demo.rescuesync.org",
        RolUsuario.OPERADOR_MUNICIPAL,
        municipio,
    )
    coordinador = _usuario(
        session,
        "coordinador@rescuesync.org",
        "coordinador@demo.rescuesync.org",
        RolUsuario.COORDINADOR_REGIONAL,
        centro,
    )
    representante = _usuario(
        session,
        "ong@rescuesync.org",
        "ong@demo.rescuesync.org",
        RolUsuario.REPRESENTANTE_ONG,
        ong,
    )
    representante_red = _usuario(
        session,
        "redmedica@rescuesync.org",
        "redmedica@demo.rescuesync.org",
        RolUsuario.REPRESENTANTE_ONG,
        red_medica,
    )
    _usuario(
        session,
        "auditor@rescuesync.org",
        "auditor@demo.rescuesync.org",
        RolUsuario.AUDITOR_DIRECTIVO,
        None,
    )

    _emergencia(
        session,
        municipio,
        operador,
        None,
        GravedadEmergencia.MEDIA,
        "Arroyo Sur — datos demo",
        "Desborde preventivo informado; pendiente de revisión regional.",
        EstadoEmergencia.REGISTRADA,
    )
    publicada = _emergencia(
        session,
        municipio,
        operador,
        centro,
        GravedadEmergencia.ALTA,
        "Corredor Norte — datos demo",
        "Inundación con familias evacuadas y acceso terrestre restringido.",
        EstadoEmergencia.PUBLICADA,
    )
    lote_agua = _lote(
        session,
        publicada,
        coordinador,
        "Agua potable",
        "Agua apta para consumo inmediato.",
        Decimal(5000),
        "litros",
    )
    lote_alimentos = _lote(
        session,
        publicada,
        coordinador,
        "Alimentos",
        "Raciones no perecederas listas para distribuir.",
        Decimal(1000),
        "raciones",
    )
    lote_salud = _lote(
        session,
        publicada,
        coordinador,
        "Atención sanitaria",
        "Kits y personal para primeros auxilios.",
        Decimal(20),
        "kits",
    )
    ahora = datetime.now(UTC)
    convocatoria = _convocatoria(
        session,
        publicada,
        (lote_agua, lote_alimentos, lote_salud),
        ahora,
    )
    _oferta(
        session,
        convocatoria,
        ong,
        representante,
        lote_agua,
        lote_salud,
        ahora,
    )

    extras: list[CuentaSeed] = []
    demo_emergencias = demo_lotes = demo_ofertas = 0
    if incluir_dashboard:
        from app.scripts.seed_auditoria import ampliar_demo_auditoria

        municipios_demo = [(municipio, operador)]
        for sufijo, nombre in [
            ("rio", "Municipalidad de Villa del Río"),
            ("sierra", "Municipalidad de Sierra Clara"),
        ]:
            organizacion_demo = _organizacion(
                session, TipoOrganizacion.MUNICIPIO, nombre
            )
            email_demo = f"municipio-{sufijo}@rescuesync.org"
            operador_demo = _usuario(
                session,
                email_demo,
                email_demo,
                RolUsuario.OPERADOR_MUNICIPAL,
                organizacion_demo,
            )
            municipios_demo.append((organizacion_demo, operador_demo))
            extras.append(CuentaSeed(email_demo, RolUsuario.OPERADOR_MUNICIPAL, nombre))
        demo_emergencias, demo_lotes, demo_ofertas = ampliar_demo_auditoria(
            session,
            municipios_demo,
            centro,
            coordinador,
            [(ong, representante), (red_medica, representante_red)],
            ahora,
        )

    return SeedResult(
        cuentas=(
            CuentaSeed(
                "municipio@rescuesync.org",
                RolUsuario.OPERADOR_MUNICIPAL,
                municipio.nombre,
            ),
            CuentaSeed(
                "coordinador@rescuesync.org",
                RolUsuario.COORDINADOR_REGIONAL,
                centro.nombre,
            ),
            CuentaSeed(
                "ong@rescuesync.org",
                RolUsuario.REPRESENTANTE_ONG,
                ong.nombre,
            ),
            CuentaSeed(
                "redmedica@rescuesync.org",
                RolUsuario.REPRESENTANTE_ONG,
                red_medica.nombre,
            ),
            CuentaSeed(
                "auditor@rescuesync.org",
                RolUsuario.AUDITOR_DIRECTIVO,
                None,
            ),
            CuentaSeed(
                administrador.email,
                RolUsuario.ADMINISTRADOR,
                None,
            ),
        )
        + tuple(extras),
        emergencias=2 + demo_emergencias,
        lotes_publicados=3 + demo_lotes,
        ofertas=1 + demo_ofertas,
    )


def main() -> int:
    """Carga el escenario demo y muestra únicamente identidades no sensibles."""

    if get_settings().app_env.casefold() == "production":
        print(
            "El seed de demostración no puede ejecutarse en producción.",
            file=sys.stderr,
        )
        return 1

    try:
        with SessionLocal.begin() as session:
            resultado = seed_development_data(session)
    except IntegrityError:
        print(
            "No se pudo cargar el seed por una restricción de los datos.",
            file=sys.stderr,
        )
        return 1
    except ValueError as error:
        print(f"No se pudo cargar el seed: {error}", file=sys.stderr)
        return 1
    print(
        "Seed de desarrollo listo con acceso técnico nacional demo. Usuarios disponibles:"
    )
    for cuenta in resultado.cuentas:
        contexto = f" — {cuenta.organizacion}" if cuenta.organizacion else ""
        print(f"- {cuenta.email} — {cuenta.rol.value}{contexto}")
    print(
        f"Datos: {resultado.emergencias} emergencias, "
        f"{resultado.lotes_publicados} lotes publicados y "
        f"{resultado.ofertas} ofertas."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
