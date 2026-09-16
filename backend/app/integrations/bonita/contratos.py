"""Contratos tipados entre FastAPI y el proceso RescueSync desplegado en Bonita.

Los nombres de entradas, actores y tareas reflejan el artefacto
`docs/RescueSync-1.1.bar`. Un cambio en el proceso obliga a actualizar este
módulo, sus pruebas RESPX y la prueba E2E contra el Runtime.
"""

from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.db.models.enums import GravedadEmergencia

TAREA_GENERAR_LOTES: Final = "Generar lotes de necesidades"
"""Primera tarea humana del Coordinador, completada al publicar la convocatoria."""

USUARIO_ACTOR_COORDINADOR: Final = "coordinador.regional"
"""Usuario asignado al actor Coordinador Regional en `actorMapping.xml`."""

GRAVEDADES_ADMITIDAS_POR_PROCESO: Final = frozenset(
    {GravedadEmergencia.BAJA, GravedadEmergencia.MEDIA, GravedadEmergencia.ALTA}
)
"""Valores aceptados por la restricción `gravedadNotNull` del contrato 1.1."""

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

    @field_validator("gravedad")
    @classmethod
    def validar_gravedad_admitida(
        cls, gravedad: GravedadEmergencia
    ) -> GravedadEmergencia:
        """Detecta antes del POST los valores que el proceso rechazaría."""

        if gravedad not in GRAVEDADES_ADMITIDAS_POR_PROCESO:
            raise ValueError(
                f"el proceso desplegado en Bonita no admite la gravedad {gravedad}"
            )
        return gravedad

    def a_payload(self) -> dict[str, int | str]:
        """Serializa las entradas con los nombres exactos del contrato."""

        return {
            "idEmergencia": self.id_emergencia,
            "gravedad": self.gravedad.value,
            "zona": self.zona,
            "descripcion": self.descripcion,
            "municipioId": self.municipio_id,
        }


class DefinicionProceso(_ModeloBonita):
    """Definición de proceso devuelta por `/API/bpm/process`."""

    id: int
    name: str
    version: str
    activation_state: str = Field(alias="activationState")
    configuration_state: str = Field(alias="configurationState")

    @property
    def lista_para_iniciar(self) -> bool:
        """Indica si el motor aceptará nuevas instancias de esta definición."""

        return (
            self.configuration_state == "RESOLVED"
            and self.activation_state == "ENABLED"
        )


class InstanciaIniciada(_ModeloBonita):
    """Respuesta de una instanciación exitosa."""

    case_id: int = Field(alias="caseId", gt=0)


class CasoBonita(_ModeloBonita):
    """Caso activo con el índice de búsqueda que lo correlaciona."""

    id: int
    process_definition_id: int = Field(alias="processDefinitionId")
    state: str
    id_emergencia_indexado: str = Field(alias="searchIndex1Value")


class TareaHumana(_ModeloBonita):
    """Tarea humana pendiente dentro de un caso."""

    id: int
    name: str
    state: str
    case_id: int = Field(alias="caseId")


class UsuarioBonita(_ModeloBonita):
    """Usuario de la organización de Bonita."""

    id: int
    user_name: str = Field(alias="userName")
