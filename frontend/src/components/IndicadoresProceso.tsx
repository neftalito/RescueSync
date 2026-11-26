import { ListadoLocal } from "./ListadoProgresivo";
import type { ReactElement, ReactNode } from "react";
import type { IndicadoresProceso as Indicadores } from "../schemas/metricas";
import { gravedadLabels } from "../schemas/emergencia";
import { formatearCantidad } from "../utils/cantidades";
import { porcentajeMonitoreo, horasMonitoreo } from "../utils/formatoMonitoreo";
import { GraficoMetricas } from "./GraficoMetricas";

export function TablaMonitoreo({ titulo, columnas, filas, vacio = "Sin hechos confirmados para los filtros seleccionados." }: {
  titulo: string; columnas: string[]; filas: ReactNode[][]; vacio?: string;
}): ReactElement {
  return <article className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 sm:p-6">
    <h3 className="text-lg font-bold text-slate-900">{titulo}</h3>
    {filas.length === 0 ? <p className="mt-3 text-sm text-slate-600">{vacio}</p> :
      <ListadoLocal items={filas} etiqueta={titulo} className="mt-3">
        {(visibles) => (
          <table className="w-full text-left text-sm">
            <caption className="sr-only">{titulo}</caption>
            <thead className="sticky top-0 bg-white"><tr>{columnas.map(c => <th key={c} className="px-3 py-2">{c}</th>)}</tr></thead>
            <tbody>{visibles.map((fila, i) => <tr key={i} className="border-t border-slate-100">{fila.map((celda, j) => <td key={j} className="px-3 py-3 tabular-nums">{celda}</td>)}</tr>)}</tbody>
          </table>
        )}
      </ListadoLocal>}
  </article>;
}

export function IndicadoresProceso({ datos }: { datos: Indicadores; }): ReactElement {
  const cobertura = datos.cobertura_cierres;
  return <section aria-labelledby="indicadores-proceso" className="min-w-0 space-y-4">
    <h3 id="indicadores-proceso" className="text-xl font-bold text-slate-900">Resultados del proceso</h3>
    <p className="text-sm text-slate-600">{datos.emergencias_con_hechos} emergencias con hechos confirmados · {datos.emergencias_sin_hechos} sin evidencia de resultados. Los casos sin evidencia no aportan tiempos ni porcentajes de cumplimiento.</p>
    <TablaMonitoreo titulo="Resolución por gravedad" columnas={["Gravedad", "Emergencias", "Resueltas", "Cierres confirmados", "Sin evidencia de cierre", "Tasa de resolución", "Con plazo", "En término", "Tiempo medio", "Tiempo medio en término"]}
      filas={datos.resolucion_por_gravedad.map(r => [gravedadLabels[r.gravedad], r.emergencias, r.resueltas, r.cierres_confirmados, r.resueltas_sin_cierre, porcentajeMonitoreo(r.tasa_resolucion), r.con_plazo, porcentajeMonitoreo(r.tasa_en_termino), horasMonitoreo(r.promedio_segundos), horasMonitoreo(r.promedio_en_termino_segundos)])} />
    {datos.resolucion_por_gravedad.some(r => r.tasa_en_termino !== null) && <GraficoMetricas titulo="Resolución en término por gravedad" unidad="%" datos={datos.resolucion_por_gravedad.filter(r => r.tasa_en_termino !== null).map(r => ({ nombre: gravedadLabels[r.gravedad], valor: r.tasa_en_termino ?? 0 }))} />}
    <TablaMonitoreo titulo="Reaperturas y reformulaciones" columnas={["Emergencia", "Reaperturas", "Reformulaciones"]}
      filas={datos.reiteradas.map(r => [`#${r.emergencia_id}`, r.reaperturas, r.reformulaciones])} />
    <TablaMonitoreo titulo="ONG por recursos adjudicados y cumplimiento" columnas={["ONG", "Capacidad", "Unidad", "Cantidad adjudicada", "Aportes", "Finalizados", "Pendientes", "Finalizados con plazo", "Cumplimiento en término"]}
      filas={datos.ranking_ongs.map(r => [r.ong, r.capacidad, r.unidad, formatearCantidad(r.cantidad), r.aportes, r.finalizados, r.aportes - r.finalizados, r.con_plazo_finalizados, porcentajeMonitoreo(r.tasa_cumplimiento)])} />
    <TablaMonitoreo titulo="Cobertura efectiva al cierre" columnas={["Cobertura", "Cierres", "Proporción"]}
      filas={cobertura.total + cobertura.parcial === 0 ? [] : [["Total", cobertura.total, porcentajeMonitoreo(cobertura.proporcion_total)], ["Parcial", cobertura.parcial, porcentajeMonitoreo(cobertura.proporcion_parcial)]]} />
    <TablaMonitoreo titulo="Demanda e inhabilitación por rubro" columnas={["Capacidad", "Unidad", "Necesidad publicada", "Evaluaciones ONG/lote", "Inhabilitadas", "Tasa de inhabilitación"]}
      filas={datos.demanda_rubros.map(r => [r.capacidad, r.unidad, formatearCantidad(r.cantidad), r.evaluaciones, r.inhabilitadas, porcentajeMonitoreo(r.tasa_inhabilitacion)])} />
    <article className="rounded-2xl border border-slate-200 bg-white p-5">
      <h3 className="text-lg font-bold text-slate-900">De la alerta a la primera adjudicación efectiva</h3>
      <p className="mt-2 text-2xl font-bold text-cyan-800">{horasMonitoreo(datos.alerta_adjudicacion_promedio_segundos)}</p>
      <p className="text-sm text-slate-600">{datos.alerta_adjudicacion_muestras} emergencias con adjudicación confirmada.</p>
    </article>
    <details className="rounded-xl border border-slate-200 bg-white p-4">
      <summary className="cursor-pointer font-semibold text-slate-800">Fórmulas y alcance de los indicadores</summary>
      <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-600">{datos.definiciones.map(d => <li key={d}>{d}</li>)}</ul>
    </details>
  </section>;
}
