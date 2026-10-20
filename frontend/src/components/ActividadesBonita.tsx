import type { ReactElement } from "react";
import type { ReporteTiempos } from "../schemas/metricas";
import { TablaMonitoreo } from "./IndicadoresProceso";
import { horasMonitoreo } from "../utils/formatoMonitoreo";

export function ActividadesBonita({ datos }: { datos: ReporteTiempos }): ReactElement {
  return <section aria-label="Actividad actual de Bonita" className="space-y-3">
    <p className="text-sm text-slate-600">Actividad actual: {datos.casos_activos_consultados ?? 0} casos consultados · {datos.casos_activos_con_error ?? datos.casos_vinculados} sin consulta completa. La antigüedad parte de la primera transición observable; un vencimiento ausente se muestra sin plazo.</p>
    <TablaMonitoreo titulo="Carga y espera por etapa" columnas={["Etapa", "Versión", "Tareas", "Con fecha", "Antigüedad media", "Vencidas", "Sin plazo", "Fallidas"]}
      filas={(datos.actividad_por_etapa ?? []).map(t => [t.etapa, t.version_proceso, t.tareas, t.con_fecha, horasMonitoreo(t.promedio_antiguedad_segundos), t.vencidas, t.sin_plazo, t.fallidas])} />
    <TablaMonitoreo titulo="Tareas en ejecución y pendientes" columnas={["Emergencia", "Caso", "Tarea", "Versión", "Estado", "Antigüedad", "Vencimiento"]}
      vacio={(datos.casos_activos_con_error ?? datos.casos_vinculados) > 0 ? "Consulta de actividad incompleta. No se puede afirmar que no haya tareas pendientes." : "No hay tareas activas en los casos consultados."}
      filas={(datos.tareas_activas ?? []).map(t => [`#${t.emergencia_id}`, t.case_id, `${t.etapa} (#${t.tarea_id})`, t.version_proceso, t.estado, horasMonitoreo(t.antiguedad_segundos), t.vence_en === null ? "Sin plazo" : `${t.vencida ? "Vencida · " : ""}${new Date(t.vence_en).toLocaleString("es-AR", { timeZone: "America/Argentina/Buenos_Aires" })}`])} />
  </section>;
}
