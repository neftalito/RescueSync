from enum import StrEnum


class TipoOrganizacion(StrEnum):
    """Clasifica a las organizaciones que participan de RescueSync."""

    MUNICIPIO = "MUNICIPIO"
    CENTRO_COORDINADOR = "CENTRO_COORDINADOR"
    ONG = "ONG"


class RolUsuario(StrEnum):
    """Define los permisos funcionales principales de un usuario local."""

    OPERADOR_MUNICIPAL = "OPERADOR_MUNICIPAL"
    COORDINADOR_REGIONAL = "COORDINADOR_REGIONAL"
    REPRESENTANTE_ONG = "REPRESENTANTE_ONG"
    AUDITOR_DIRECTIVO = "AUDITOR_DIRECTIVO"
    ADMINISTRADOR = "ADMINISTRADOR"


class GravedadEmergencia(StrEnum):
    """Representa la severidad informada al registrar una emergencia."""

    BAJA = "BAJA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    CRITICA = "CRITICA"


class EstadoEmergencia(StrEnum):
    """Representa el avance local del ciclo de vida de una emergencia."""

    REGISTRADA = "REGISTRADA"
    EN_COORDINACION = "EN_COORDINACION"
    PUBLICADA = "PUBLICADA"
    EN_EVALUACION = "EN_EVALUACION"
    EN_EJECUCION = "EN_EJECUCION"
    RESUELTA = "RESUELTA"
    CANCELADA = "CANCELADA"


class EstadoSincronizacionBonita(StrEnum):
    """Describe el resultado conocido de vincular una emergencia con Bonita."""

    PENDIENTE = "PENDIENTE"
    VINCULADA = "VINCULADA"
    ERROR = "ERROR"
    RESULTADO_DESCONOCIDO = "RESULTADO_DESCONOCIDO"


class EstadoTareaBonita(StrEnum):
    """Resultado conocido de completar una tarea humana de Bonita al publicar."""

    PENDIENTE = "PENDIENTE"
    EN_PROGRESO = "EN_PROGRESO"
    COMPLETADA = "COMPLETADA"
    ERROR = "ERROR"
    RESULTADO_DESCONOCIDO = "RESULTADO_DESCONOCIDO"


class EstadoLote(StrEnum):
    """Controla si un lote todavía puede editarse o ya fue publicado."""

    BORRADOR = "BORRADOR"
    PUBLICADO = "PUBLICADO"
    CERRADO = "CERRADO"
    CANCELADO = "CANCELADO"


class EstadoConvocatoria(StrEnum):
    """Representa la disponibilidad de una ventana de recepción de ofertas."""

    ABIERTA = "ABIERTA"
    CERRADA = "CERRADA"
    CANCELADA = "CANCELADA"


class EstadoOferta(StrEnum):
    """Representa el ciclo de vida local de una oferta de ayuda."""

    BORRADOR = "BORRADOR"
    PRESENTADA = "PRESENTADA"
    EN_VALIDACION = "EN_VALIDACION"
    VALIDADA = "VALIDADA"
    ADJUDICADA = "ADJUDICADA"
    NO_ADJUDICADA = "NO_ADJUDICADA"
    RETIRADA = "RETIRADA"


class TipoAporte(StrEnum):
    """Distingue la naturaleza del aporte incluido en una oferta."""

    RECURSO = "RECURSO"
    PERSONAL = "PERSONAL"
    MIXTO = "MIXTO"


class TipoParticipacion(StrEnum):
    """Define el rol de una ONG dentro de una oferta conjunta."""

    LIDER = "LIDER"
    MIEMBRO = "MIEMBRO"


class TipoNotificacion(StrEnum):
    """Clasifica las novedades operativas que recibe un usuario."""

    EMERGENCIA_REGISTRADA = "EMERGENCIA_REGISTRADA"
    EMERGENCIA_ESTADO_ACTUALIZADO = "EMERGENCIA_ESTADO_ACTUALIZADO"
    CONVOCATORIA_PUBLICADA = "CONVOCATORIA_PUBLICADA"
    CONVOCATORIA_ACTUALIZADA = "CONVOCATORIA_ACTUALIZADA"
    CONVOCATORIA_CERRADA = "CONVOCATORIA_CERRADA"
    OFERTA_RECIBIDA = "OFERTA_RECIBIDA"
    TAREA_BONITA_FALLIDA = "TAREA_BONITA_FALLIDA"


class TipoOperacion(StrEnum):
    COMPROMISO = "COMPROMISO"
    LIBERACION = "LIBERACION"
    CIERRE = "CIERRE"


class EstadoOperacion(StrEnum):
    PENDIENTE = "PENDIENTE"
    INCIERTO = "INCIERTO"
    TEMPORAL = "TEMPORAL"
    CONFIGURACION = "CONFIGURACION"
    RECHAZO_DEFINITIVO = "RECHAZO_DEFINITIVO"
    CONFIRMADA = "CONFIRMADA"
