"""Carga sintética para medir listados y consultas sin iniciar procesos BPM."""

import argparse
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from itertools import batched
from time import perf_counter
from uuid import NAMESPACE_URL, UUID, uuid5

from faker import Faker
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
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
    Notificacion,
    Oferta,
    OfertaItem,
    OfertaItemAporte,
    OfertaParticipante,
    OfertaVersion,
    OfertaVersionParticipante,
    Organizacion,
    RolUsuario,
    TipoAporte,
    TipoNotificacion,
    TipoOrganizacion,
    TipoParticipacion,
    Usuario,
)
from app.db.session import SessionLocal
from app.services.acceso_nacional import cifrador

# Credenciales exclusivamente sintéticas, compartidas con el seed nacional.
PASSWORD_PRUEBA = "CargaMasiva2026!"
PASSWORD_TECNICA = "CargaMasivaTecnica2026!"
CAPACIDADES = (
    ("AGUA", "Agua potable", "litros", True),
    ("RACIONES", "Raciones de alimento listas para consumo", "raciones", False),
    ("PARAMEDICOS", "Personal paramédico", "personas", False),
    ("AMBULANCIAS", "Ambulancias", "vehículos", False),
)
ESTADOS = (
    EstadoEmergencia.REGISTRADA,
    EstadoEmergencia.EN_COORDINACION,
    EstadoEmergencia.PUBLICADA,
    EstadoEmergencia.EN_EVALUACION,
    EstadoEmergencia.CANCELADA,
)


@dataclass(frozen=True)
class ConfiguracionSeed:
    """Los conteos son objetivos totales por seed, no incrementos por ejecución."""

    seed: int = 2026
    municipios: int = 100
    centros: int = 10
    ongs: int = 1000
    emergencias: int = 5000
    lotes_por_emergencia: int = 3
    ofertas_por_convocatoria: int = 3
    batch_size: int = 250

    def __post_init__(self) -> None:
        if not 0 <= self.seed <= 2_147_483_647:
            raise ValueError("seed debe estar entre 0 y 2147483647.")
        for nombre, valor in asdict(self).items():
            if nombre != "seed" and valor <= 0:
                raise ValueError(f"{nombre} debe ser positivo.")
        if self.batch_size > 1000:
            raise ValueError("batch_size no puede superar 1000.")
        if self.ofertas_por_convocatoria > self.ongs:
            raise ValueError("Las ofertas por convocatoria no pueden superar las ONGs.")


@dataclass
class ResultadoSeed:
    organizaciones: int = 0
    usuarios: int = 0
    emergencias: int = 0
    omitidas: int = 0
    lotes: int = 0
    convocatorias: int = 0
    ofertas: int = 0
    notificaciones: int = 0


@dataclass(frozen=True)
class Identidad:
    organizacion: Organizacion
    usuario: Usuario
    indice: int


def id_nacional(seed: int, referencia: str) -> UUID:
    """Comparte UUIDs explícitos con RescueSyncAPI, sin consultar su base."""
    return uuid5(NAMESPACE_URL, f"rescuesync-masivo:{seed}:{referencia}")


def _usuario(
    session: Session,
    email: str,
    rol: RolUsuario,
    organizacion: Organizacion | None,
    password_hash: str,
) -> tuple[Usuario, bool]:
    usuario = session.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
    organizacion_id = organizacion.id if organizacion else None
    if usuario is not None:
        if usuario.rol != rol or usuario.organizacion_id != organizacion_id:
            raise ValueError("Una cuenta masiva pertenece a otra identidad local.")
        return usuario, False
    usuario = Usuario(
        email=email,
        rol=rol,
        organizacion_id=organizacion_id,
        password_hash=password_hash,
    )
    session.add(usuario)
    return usuario, True


def _identidades(
    session: Session,
    config: ConfiguracionSeed,
    tipo: TipoOrganizacion,
    rol: RolUsuario,
    cantidad: int,
    password_hash: str,
    resultado: ResultadoSeed,
) -> list[Identidad]:
    identidades: list[Identidad] = []
    cifrado = cifrador()
    for indices in batched(range(1, cantidad + 1), config.batch_size, strict=False):
        nombres = {i: f"Masivo {config.seed} {tipo.value} {i:06d}" for i in indices}
        existentes = {
            org.nombre: org
            for org in session.scalars(
                select(Organizacion).where(
                    Organizacion.tipo == tipo,
                    Organizacion.nombre.in_(nombres.values()),
                )
            )
        }
        organizaciones: list[Organizacion] = []
        for i, nombre in nombres.items():
            org = existentes.get(nombre)
            ong_id = id_nacional(config.seed, f"ong:{i}")
            if org is None:
                org = Organizacion(
                    nombre=nombre,
                    tipo=tipo,
                    ong_nacional_id=ong_id if tipo == TipoOrganizacion.ONG else None,
                )
                session.add(org)
                resultado.organizaciones += 1
            elif tipo == TipoOrganizacion.ONG and org.ong_nacional_id != ong_id:
                raise ValueError("Una ONG masiva tiene otra vinculación nacional.")
            organizaciones.append(org)
        session.flush()
        for i, org in zip(indices, organizaciones, strict=True):
            email = f"masivo-{config.seed}-{tipo.value.lower()}-{i}@example.test"
            usuario, creado = _usuario(session, email, rol, org, password_hash)
            resultado.usuarios += creado
            identidades.append(Identidad(org, usuario, i))
            if tipo != TipoOrganizacion.ONG:
                continue
            acceso = session.get(AccesoNacional, org.id)
            cuenta_id = id_nacional(config.seed, f"cuenta-tecnica:{i}")
            if acceso is not None:
                if (
                    acceso.ong_id != org.ong_nacional_id
                    or acceso.cuenta_id != cuenta_id
                ):
                    raise ValueError(
                        "El acceso masivo pertenece a otra cuenta nacional."
                    )
                continue
            session.add(
                AccesoNacional(
                    organizacion_id=org.id,
                    ong_id=org.ong_nacional_id,
                    cuenta_id=cuenta_id,
                    configuracion_id=id_nacional(config.seed, f"configuracion:{i}"),
                    identificador_login=f"masivo-{config.seed}-tecnica-{i}",
                    secreto_cifrado=cifrado.encrypt(PASSWORD_TECNICA.encode()).decode(),
                    requiere_revision=False,
                )
            )
        session.flush()
    return identidades


@dataclass(frozen=True)
class Publicacion:
    indice: int
    convocatoria: Convocatoria
    lotes: list[Lote]


def _ofertas(
    session: Session,
    config: ConfiguracionSeed,
    publicaciones: list[Publicacion],
    ongs: list[Identidad],
) -> None:
    """Inserta cada nivel en bloque y presenta sólo al terminar el desglose."""
    propuestas: list[tuple[Oferta, Identidad, Publicacion]] = []
    for publicacion in publicaciones:
        for j in range(config.ofertas_por_convocatoria):
            ong = ongs[(publicacion.indice - 1 + j) % len(ongs)]
            oferta = Oferta(
                convocatoria_id=publicacion.convocatoria.id,
                ong_creadora_id=ong.organizacion.id,
                creada_por_usuario_id=ong.usuario.id,
                estado=EstadoOferta.PRESENTADA,
                creada_en=publicacion.convocatoria.publicada_en,
            )
            session.add(oferta)
            propuestas.append((oferta, ong, publicacion))
    session.flush()
    versiones: list[OfertaVersion] = []
    for oferta, ong, publicacion in propuestas:
        version = OfertaVersion(
            oferta_id=oferta.id,
            creada_por_usuario_id=ong.usuario.id,
            numero=1,
            requiere_desglose_nacional=True,
            observaciones="Oferta sintética para pruebas de volumen.",
            creada_en=publicacion.convocatoria.publicada_en,
        )
        session.add(version)
        versiones.append(version)
    session.flush()
    aportes: list[tuple[OfertaItem, OfertaVersion, Identidad, Lote, int]] = []
    for (oferta, ong, publicacion), version in zip(propuestas, versiones, strict=True):
        session.add(
            OfertaParticipante(
                oferta_id=oferta.id,
                ong_id=ong.organizacion.id,
                rol=TipoParticipacion.LIDER,
            )
        )
        session.add(
            OfertaVersionParticipante(
                oferta_version_id=version.id,
                ong_id=ong.organizacion.id,
                ong_nacional_id=ong.organizacion.ong_nacional_id,
                nombre_ong=ong.organizacion.nombre,
                rol=TipoParticipacion.LIDER,
                confirmada_en=publicacion.convocatoria.publicada_en,
            )
        )
        for j, lote in enumerate(publicacion.lotes):
            item = OfertaItem(
                oferta_version_id=version.id,
                convocatoria_id=publicacion.convocatoria.id,
                lote_id=lote.id,
                tipo=TipoAporte.PERSONAL
                if lote.unidad == "personas"
                else TipoAporte.RECURSO,
                descripcion=f"Aporte sintético: {lote.tipo_necesidad}",
                cantidad_ofrecida=Decimal(10),
                unidad=lote.unidad,
            )
            session.add(item)
            aportes.append((item, version, ong, lote, j))
    session.flush()
    for item, version, ong, lote, j in aportes:
        session.add(
            OfertaItemAporte(
                oferta_item_id=item.id,
                oferta_version_id=version.id,
                ong_id=ong.organizacion.id,
                recurso_nacional_id=id_nacional(
                    config.seed, f"recurso:{ong.indice}:{j % len(CAPACIDADES) + 1}"
                ),
                capacidad_nacional_id=lote.capacidad_nacional_id,
                cantidad=item.cantidad_ofrecida,
                unidad=item.unidad,
            )
        )
    session.flush()
    for (_, _, publicacion), version in zip(propuestas, versiones, strict=True):
        version.presentada_en = publicacion.convocatoria.publicada_en
    session.flush()


def _escenarios(
    session: Session,
    config: ConfiguracionSeed,
    nuevas: list[tuple[int, Emergencia, Identidad]],
    ongs: list[Identidad],
    ahora: datetime,
    resultado: ResultadoSeed,
) -> None:
    """Procesa las relaciones de toda una tanda sin consultas por emergencia."""
    publicaciones: list[Publicacion] = []
    for indice, emergencia, coordinador in nuevas:
        estado = emergencia.estado
        if estado in {EstadoEmergencia.REGISTRADA, EstadoEmergencia.CANCELADA}:
            continue
        publicada = estado != EstadoEmergencia.EN_COORDINACION
        lotes: list[Lote] = []
        for j in range(config.lotes_por_emergencia):
            codigo, nombre, unidad, fracciones = CAPACIDADES[j % len(CAPACIDADES)]
            lote = Lote(
                emergencia_id=emergencia.id,
                creado_por_usuario_id=coordinador.usuario.id,
                tipo_necesidad=f"{nombre} / {j + 1}",
                descripcion="Necesidad sintética para medir consultas con volumen.",
                cantidad_requerida=Decimal(100 * config.ofertas_por_convocatoria),
                unidad=unidad,
                capacidad_nacional_id=uuid5(
                    NAMESPACE_URL, f"rescuesync:capacidad:{codigo}"
                ),
                codigo_capacidad=codigo,
                admite_fracciones=fracciones,
                riesgo_requerido=emergencia.gravedad,
                estado=EstadoLote.PUBLICADO if publicada else EstadoLote.BORRADOR,
                creado_en=emergencia.creada_en,
            )
            session.add(lote)
            lotes.append(lote)
        resultado.lotes += len(lotes)
        if not publicada:
            continue
        abierta = estado == EstadoEmergencia.PUBLICADA
        fecha = emergencia.creada_en + timedelta(hours=1)
        cierre = ahora + timedelta(days=30) if abierta else fecha + timedelta(hours=12)
        convocatoria = Convocatoria(
            emergencia_id=emergencia.id,
            numero=1,
            sistema_origen_ref=f"masivo-{config.seed}",
            gravedad_publicada=emergencia.gravedad,
            estado=EstadoConvocatoria.ABIERTA
            if abierta
            else EstadoConvocatoria.CERRADA,
            publicada_en=fecha,
            cierra_en=cierre,
            cerrada_en=None if abierta else cierre,
        )
        session.add(convocatoria)
        publicaciones.append(Publicacion(indice, convocatoria, lotes))
    session.flush()
    for publicacion in publicaciones:
        for lote in publicacion.lotes:
            session.add(
                ConvocatoriaLote(
                    convocatoria_id=publicacion.convocatoria.id,
                    lote_id=lote.id,
                    cantidad_publicada=lote.cantidad_requerida,
                    unidad_publicada=lote.unidad,
                    capacidad_nacional_id=lote.capacidad_nacional_id,
                    codigo_capacidad_publicada=lote.codigo_capacidad,
                    admite_fracciones_publicada=lote.admite_fracciones,
                    riesgo_requerido_publicado=lote.riesgo_requerido,
                )
            )
    session.flush()
    _ofertas(session, config, publicaciones, ongs)
    resultado.convocatorias += len(publicaciones)
    resultado.ofertas += len(publicaciones) * config.ofertas_por_convocatoria


def seed_mass_data(
    session: Session,
    config: ConfiguracionSeed,
    *,
    progreso: Callable[[str], None] | None = None,
) -> ResultadoSeed:
    """Agrega escenarios faltantes; el llamador confirma o revierte toda la carga."""
    if get_settings().app_env.casefold() not in {"development", "test"}:
        raise ValueError("El seed masivo sólo está disponible en desarrollo y pruebas.")
    if get_settings().nacional_encryption_key is None:
        raise ValueError("Configurá NACIONAL_ENCRYPTION_KEY antes de ejecutar el seed.")
    # La zona no es UNIQUE: serializar este dataset evita duplicados concurrentes.
    session.execute(select(func.pg_advisory_xact_lock(73842, config.seed)))
    # Cada versión se presenta después de insertar todo su desglose. Validarla
    # entonces evita que cada evento diferido vuelva a recorrerla durante COMMIT.
    session.execute(
        text(
            "SET CONSTRAINTS validar_desglose_version, validar_desglose_participante, "
            "validar_desglose_item, validar_desglose_aporte IMMEDIATE"
        )
    )
    resultado = ResultadoSeed()
    password_hash = generar_password_hash(PASSWORD_PRUEBA)
    municipios = _identidades(
        session,
        config,
        TipoOrganizacion.MUNICIPIO,
        RolUsuario.OPERADOR_MUNICIPAL,
        config.municipios,
        password_hash,
        resultado,
    )
    centros = _identidades(
        session,
        config,
        TipoOrganizacion.CENTRO_COORDINADOR,
        RolUsuario.COORDINADOR_REGIONAL,
        config.centros,
        password_hash,
        resultado,
    )
    ongs = _identidades(
        session,
        config,
        TipoOrganizacion.ONG,
        RolUsuario.REPRESENTANTE_ONG,
        config.ongs,
        password_hash,
        resultado,
    )
    for nombre, rol in (
        ("admin", RolUsuario.ADMINISTRADOR),
        ("auditor", RolUsuario.AUDITOR_DIRECTIVO),
    ):
        _, creado = _usuario(
            session,
            f"masivo-{config.seed}-{nombre}@example.test",
            rol,
            None,
            password_hash,
        )
        resultado.usuarios += creado
    session.flush()
    if progreso:
        progreso("Identidades preparadas; cargando emergencias y sus relaciones...")
    fake = Faker("es_AR", use_weighting=False)
    ahora = datetime.now(UTC)
    gravedades = tuple(GravedadEmergencia)
    for indices in batched(
        range(1, config.emergencias + 1), config.batch_size, strict=False
    ):
        zonas = {i: f"Masivo {config.seed} emergencia {i:08d}" for i in indices}
        existentes = set(
            session.scalars(
                select(Emergencia.zona).where(Emergencia.zona.in_(zonas.values()))
            )
        )
        nuevas: list[tuple[int, Emergencia, Identidad]] = []
        for i, zona in zonas.items():
            if zona in existentes:
                resultado.omitidas += 1
                continue
            fake.seed_instance(f"{config.seed}:emergencia:{i}")
            grupo = (i - 1) // len(ESTADOS)
            municipio = municipios[grupo % len(municipios)]
            centro = centros[grupo % len(centros)]
            estado = ESTADOS[(i - 1) % len(ESTADOS)]
            emergencia = Emergencia(
                municipio_id=municipio.organizacion.id,
                creada_por_usuario_id=municipio.usuario.id,
                centro_coordinador_id=None
                if estado == EstadoEmergencia.REGISTRADA
                else centro.organizacion.id,
                gravedad=gravedades[(i - 1) % len(gravedades)],
                zona=zona,
                descripcion=f"Escenario sintético en {fake.city()}, {fake.street_address()}. {fake.paragraph()}",
                estado=estado,
                creada_en=ahora - timedelta(days=fake.random_int(min=1, max=180)),
            )
            session.add(emergencia)
            nuevas.append((i, emergencia, centro))
        session.flush()
        _escenarios(session, config, nuevas, ongs, ahora, resultado)
        for i, emergencia, centro in nuevas:
            session.add(
                Notificacion(
                    usuario_id=centro.usuario.id,
                    clave_evento=f"masivo:{config.seed}:emergencia:{i}",
                    tipo=TipoNotificacion.EMERGENCIA_REGISTRADA,
                    titulo="Emergencia sintética registrada",
                    mensaje=emergencia.descripcion,
                    ruta=f"/emergencias/{emergencia.id}/lotes",
                    creada_en=emergencia.creada_en,
                )
            )
        session.flush()
        resultado.emergencias += len(nuevas)
        resultado.notificaciones += len(nuevas)
        if progreso:
            progreso(
                f"Emergencias procesadas: {indices[-1]}/{config.emergencias} (sin commit todavía)."
            )
    return resultado


def main(argv: list[str] | None = None) -> int:
    """Expone cantidades, simulación sin base y resumen de filas nuevas."""
    parser = argparse.ArgumentParser(description=__doc__)
    for nombre, defecto in asdict(ConfiguracionSeed()).items():
        parser.add_argument(f"--{nombre.replace('_', '-')}", type=int, default=defecto)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra la configuración sin conectar a la base.",
    )
    args = vars(parser.parse_args(argv))
    dry_run = args.pop("dry_run")
    try:
        config = ConfiguracionSeed(**args)
        if get_settings().app_env.casefold() not in {"development", "test"}:
            raise ValueError(
                "El seed masivo sólo está disponible en desarrollo y pruebas."
            )
        if dry_run:
            print(f"Simulación sin escrituras: {asdict(config)}")
            return 0
        inicio = perf_counter()
        with SessionLocal.begin() as session:
            resultado = seed_mass_data(session, config, progreso=print)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "No se pudo completar la carga; se revirtió la transacción. "
            "Revisá la conexión, migraciones y posibles colisiones.",
            file=sys.stderr,
        )
        return 1
    print(f"Carga confirmada en {perf_counter() - inicio:.1f}s: {asdict(resultado)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
