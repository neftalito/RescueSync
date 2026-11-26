"""Contratos tipados entre FastAPI y el proceso RescueSync desplegado en Bonita.

Los nombres de entradas, actores, tareas y parámetros reflejan el artefacto
`docs/RescueSync-1.5.bar`. Un cambio en el proceso obliga a publicar un `.bar`
con otra versión y actualizar, en el mismo cambio, este módulo, sus pruebas
RESPX y la prueba E2E contra el Runtime.
"""

from typing import Annotated, Final, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    StringConstraints,
)

from app.db.models.enums import GravedadEmergencia

PARAMETRO_CALLBACK_TOKEN: Final = "callbackToken"
"""Parámetro del proceso que Bonita envía como `Authorization: Bearer`."""

CABECERA_CASO_RAIZ: Final = "X-Bonita-Root-Process-Instance-Id"
"""Cabecera de contexto que los conectores REST agregan a cada callback."""

TAREA_GENERAR_LOTES: Final = "Generar lotes de necesidades"
"""Primera tarea humana del Coordinador, completada al publicar la convocatoria."""

USUARIO_ACTOR_COORDINADOR: Final = "coordinador.regional"
"""Usuario asignado al actor Coordinador Regional en `actorMapping.xml`."""

TextoNoVacio = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]


class _ModeloBonita(BaseModel):
    """Base de los modelos que Bonita serializa en camelCase."""

    model_config = ConfigDict(frozen=True, extra="ignore", validate_by_name=True)


class ContratoInicioProceso(_ModeloBonita):
    """Entradas del contrato de instanciación de RescueSync."""

    id_emergencia: int = Field(alias="idEmergencia", gt=0)
    gravedad: GravedadEmergencia
    zona: Annotated[TextoNoVacio, StringConstraints(max_length=255)]
    descripcion: TextoNoVacio
    municipio_id: int = Field(alias="municipioId", gt=0)

    def a_payload(self) -> dict[str, int | str]:
        """Serializa las entradas con los nombres exactos del contrato."""

        return {
            "idEmergencia": self.id_emergencia,
            "gravedad": self.gravedad.value,
            "zona": self.zona,
            "descripcion": self.descripcion,
            "municipioId": self.municipio_id,
        }


class ContratoDecision(_ModeloBonita):
    """Entradas acordadas para el próximo export de Studio, posterior a 1.5."""

    accion_seleccionada: Literal["REABRIR", "REFORMULAR", "CONTINUAR_PARCIAL"] = Field(
        alias="accionSeleccionada"
    )
    decision_coordinador_id: UUID = Field(alias="decisionCoordinadorId")


class ContratoSeleccion(_ModeloBonita):
    adjudicacion_id: UUID = Field(alias="adjudicacionId")
    adjudicacion_version: PositiveInt = Field(alias="adjudicacionVersion")
    convocatoria_id: PositiveInt = Field(alias="convocatoriaId")
    operacion_compromiso_id: UUID = Field(alias="operacionCompromisoId")


class ContratoFinalizacion(_ModeloBonita):
    participacion_id: UUID = Field(alias="participacionId")
    finalizacion_id: UUID = Field(alias="finalizacionId")


class ContratoCierre(_ModeloBonita):
    solicitud_cierre_id: UUID = Field(alias="solicitudCierreId")


class ContratoRecuperacion(_ModeloBonita):
    accion_incidente: Literal["REINTENTAR_MISMA_OPERACION", "VOLVER_A_SELECCION"] = (
        Field(alias="accionIncidente")
    )
    operacion_id: UUID = Field(alias="operacionId")


class DefinicionProceso(_ModeloBonita):
    """Definición de proceso devuelta por `/API/bpm/process`."""

    id: PositiveInt
    name: TextoNoVacio
    version: TextoNoVacio
    activation_state: Literal["ENABLED", "DISABLED"] = Field(alias="activationState")
    configuration_state: Literal["RESOLVED", "UNRESOLVED"] = Field(
        alias="configurationState"
    )

    @property
    def lista_para_iniciar(self) -> bool:
        """Indica si el motor aceptará nuevas instancias de esta definición."""

        return (
            self.configuration_state == "RESOLVED"
            and self.activation_state == "ENABLED"
        )


class InstanciaIniciada(_ModeloBonita):
    """Respuesta de una instanciación exitosa."""

    case_id: PositiveInt = Field(alias="caseId")


class CasoBonita(_ModeloBonita):
    """Caso activo con el índice de búsqueda que lo correlaciona."""

    id: PositiveInt
    process_definition_id: PositiveInt = Field(alias="processDefinitionId")
    state: TextoNoVacio
    etiqueta_id_emergencia: str = Field(alias="searchIndex1Label")
    id_emergencia_indexado: str = Field(alias="searchIndex1Value")


class TareaHumana(_ModeloBonita):
    """Tarea humana pendiente dentro de un caso."""

    id: PositiveInt
    name: TextoNoVacio
    state: TextoNoVacio
    case_id: PositiveInt = Field(alias="caseId")


class UsuarioBonita(_ModeloBonita):
    """Usuario de la organización de Bonita."""

    id: PositiveInt
    user_name: TextoNoVacio = Field(alias="userName")


class TransicionTareaArchivada(_ModeloBonita):
    """Relaciona transiciones de una misma tarea, sin confundirlas con repeticiones.

    Bonita 10.4 archiva gateways sin `reached_state_date`; la fecha es opcional
    para no descartar el historial completo del caso por esas filas.
    """

    source_object_id: PositiveInt = Field(alias="sourceObjectId")
    root_case_id: PositiveInt = Field(alias="rootCaseId")
    name: str
    tipo: str = Field(alias="type")
    state: TextoNoVacio
    reached_state_date: str | None = None


class TareaBonitaFallida(_ModeloBonita):
    """Nodo fallido observado por el monitor; no expone trazas del motor."""

    id: PositiveInt
    root_case_id: PositiveInt = Field(alias="rootCaseId")
    name: str
    state: Literal["failed"]


class FechaTemporizador(_ModeloBonita):
    execution_date_ms: PositiveInt = Field(alias="executionDate")


class TemporizadorBonita(FechaTemporizador):
    """Disparo programado por el motor para un evento del caso."""

    id: PositiveInt
    name: TextoNoVacio = Field(alias="eventInstanceName")


class TareaActiva(_ModeloBonita):
    """Estado actual de un nodo, incluidos temporizadores sin fecha de transición."""

    id: PositiveInt
    root_case_id: PositiveInt = Field(alias="rootCaseId")
    name: str
    tipo: str = Field(alias="type")
    state: TextoNoVacio
    reached_state_date: str | None = None
    due_date: str | None = Field(default=None, alias="dueDate")
