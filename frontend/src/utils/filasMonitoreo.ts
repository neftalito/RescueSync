import type { ReporteMetricas, ReporteTiempos } from "../schemas/metricas";

/** Conserva todos los campos y decimales de la evidencia visible en CSV/PDF. */
export function filasMonitoreo(locales: ReporteMetricas, tiempos: ReporteTiempos | undefined): (string | number)[][] {
  const filas: (string | number)[][] = [];
  const agregar = (seccion: string, categoria: string, objeto: object): void => {
    for (const [indicador, valor] of Object.entries(objeto)) {
      if (valor === null || ["string", "number", "boolean"].includes(typeof valor))
        filas.push([seccion, indicador, categoria, valor === null ? "Sin datos" : String(valor), indicador.includes("segundos") ? "segundos" : indicador.startsWith("tasa_") || indicador.startsWith("proporcion") ? "%" : ""]);
    }
  };
  const datos = locales.indicadores_proceso;
  if (datos) {
    agregar("resultados_proceso", "", datos);
    for (const r of datos.resolucion_por_gravedad) agregar("resolucion_por_gravedad", r.gravedad, r);
    for (const r of datos.reiteradas) agregar("reiteradas", String(r.emergencia_id), r);
    for (const r of datos.ranking_ongs) agregar("ranking_ongs", `${r.ong_id} / ${r.capacidad} / ${r.unidad}`, r);
    agregar("cobertura_cierres", "", datos.cobertura_cierres);
    for (const r of datos.demanda_rubros) agregar("demanda_rubros", `${r.capacidad} / ${r.unidad}`, r);
    if (datos.suministros_movilizados) {
      agregar("suministros_movilizados", "", datos.suministros_movilizados);
      for (const r of datos.suministros_movilizados.cantidades)
        agregar("suministros_movilizados", `${r.capacidad} / ${r.unidad}`, r);
    }
    if (datos.resolucion_consorcios) agregar("resolucion_consorcios", "", datos.resolucion_consorcios);
    datos.definiciones.forEach((d, i) => filas.push(["definiciones", String(i + 1), "", d, ""]));
  }
  if (tiempos) {
    agregar("actividad_bonita", "", {
      casos_consultados: tiempos.casos_activos_consultados ?? "Sin datos",
      casos_sin_consulta: tiempos.casos_activos_con_error ?? "Sin datos",
    });
    for (const t of tiempos.tareas_activas ?? []) agregar("tareas_activas", `${t.emergencia_id} / ${t.tarea_id}`, t);
    for (const t of tiempos.actividad_por_etapa ?? []) agregar("actividad_por_etapa", `${t.etapa} / ${t.version_proceso}`, t);
  }
  return filas;
}
