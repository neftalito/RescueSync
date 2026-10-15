import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.integrations.bonita.cliente import ClienteBonita, ConfiguracionBonita
from app.integrations.email.cliente import ClienteSMTP, ConfiguracionSMTP
from app.integrations.nacional.cliente import ClienteNacional
from app.services.bootstrap import asegurar_admin_inicial
from app.services.monitor_bonita import monitorizar_bonita
from app.services.tiempo_real import GestorTiempoReal

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Comparte clientes y cierra recursos externos al apagar la API."""

    if settings.app_env.casefold() in {"development", "production"}:
        with SessionLocal.begin() as session:
            asegurar_admin_inicial(session, settings)

    gestor_tiempo_real = GestorTiempoReal()
    gestor_tiempo_real.iniciar()
    app.state.gestor_tiempo_real = gestor_tiempo_real
    app.state.cliente_email = ClienteSMTP(ConfiguracionSMTP.desde_settings(settings))
    cliente_nacional = ClienteNacional(
        str(settings.nacional_base_url), settings.nacional_timeout_seconds
    )
    app.state.cliente_nacional = cliente_nacional
    try:
        with ClienteBonita(ConfiguracionBonita.desde_settings(settings)) as cliente:
            app.state.cliente_bonita = cliente
            detener_monitor = asyncio.Event()
            monitor = (
                asyncio.create_task(
                    monitorizar_bonita(
                        cliente,
                        gestor_tiempo_real,
                        detener_monitor,
                        settings.bonita_monitor_interval_seconds,
                    )
                )
                if settings.app_env.casefold() != "test"
                and settings.bonita_monitor_enabled
                else None
            )
            try:
                yield
            finally:
                detener_monitor.set()
                if monitor is not None:
                    await monitor
    finally:
        cliente_nacional.close()
        await gestor_tiempo_real.detener()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="API local para la coordinación de emergencias de RescueSync.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.exception_handler(RequestValidationError)
async def responder_error_validacion(
    _request: Request,
    error: RequestValidationError,
) -> JSONResponse:
    """Devuelve los errores de entrada con el contrato uniforme de la API."""

    primero = error.errors()[0] if error.errors() else None
    if primero is None:
        detalle = "Los datos enviados no son válidos."
    else:
        ubicacion = primero.get("loc", ())
        partes = [str(parte) for parte in ubicacion if parte not in {"body", "query"}]
        campo = ".".join(partes) or "solicitud"
        tipo = str(primero.get("type", ""))
        mensaje = str(primero.get("msg", ""))
        if tipo == "missing":
            detalle = f"El campo {campo} es obligatorio."
        elif tipo == "value_error" and mensaje:
            detalle = mensaje.removeprefix("Value error, ")
        elif tipo == "string_too_long":
            detalle = f"El campo {campo} supera la longitud permitida."
        elif tipo == "string_too_short":
            detalle = f"El campo {campo} no puede estar vacío."
        else:
            detalle = f"El valor de {campo} no es válido."
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": detalle},
    )


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": f"{settings.api_v1_prefix}/health",
    }
