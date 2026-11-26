import { ListadoLocal } from "./ListadoProgresivo";
import type { ReactElement, ReactNode } from "react";
import type { IndicadoresProceso as Indicadores } from "../schemas/metricas";
import { gravedadLabels } from "../schemas/emergencia";
import { etiquetaUmbral, porcentajeMonitoreo, horasMonitoreo } from "../utils/formatoMonitoreo";
import { GraficoMetricas } from "./GraficoMetricas";

export function TablaMonitoreo({ titulo, columnas, filas, descripcion, vacio = "Sin hechos confirmados para los filtros seleccionados." }: {
  titulo: string; columnas: string[]; filas: ReactNode[][]; descripcion?: string; vacio?: string;
}): ReactElement {
  return <article className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 sm:p-6">
    <h3 className="text-lg font-bold text-slate-900">{titulo}</h3>
    {descripcion && <p className="mt-2 text-sm text-slate-600">{descripcion}</p>}
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

export function IndicadoresProceso({ datos, umbralAportes, umbralResolucion }: {
  datos: Indicadores;
  umbralAportes: number;
  umbralResolucion: number;
}): ReactElement {
  const cobertura = datos.cobertura_cierres;
  const movilizados = datos.suministros_movilizados;
  const consorcios = datos.resolucion_consorcios;
  const limiteAportes = etiquetaUmbral(umbralAportes);
  const limiteResolucion = etiquetaUmbral(umbralResolucion);
  const resolucionesConTiempo = datos.resolucion_por_gravedad.flatMap(
    r => r.tasa_dentro_del_umbral === null ? [] : [{
      nombre: gravedadLabels[r.gravedad], valor: r.tasa_dentro_del_umbral,
    }],
  );
  const filasCobertura: ReactNode[][] = cobertura.total + cobertura.parcial > 0
    ? [["Total", cobertura.total, porcentajeMonitoreo(cobertura.proporcion_total)], ["Parcial", cobertura.parcial, porcentajeMonitoreo(cobertura.proporcion_parcial)]]
    : [];
  return <section aria-labelledby="indicadores-proceso" className="min-w-0 space-y-4">
    <h3 id="indicadores-proceso" className="text-xl font-bold text-slate-900">Resultados del proceso</h3>
    <p className="text-sm text-slate-600">{datos.emergencias_con_hechos} emergencias con hechos confirmados · {datos.emergencias_sin_hechos} sin evidencia de resultados.</p>
    <TablaMonitoreo titulo="Resolución por gravedad"
      columnas={["Gravedad", "Emergencias", "Resueltas", "Cierres confirmados", "Sin evidencia de cierre", "Tasa de resolución", "Cierres con tiempo medido", `Cierres en hasta ${limiteResolucion}`, `% en hasta ${limiteResolucion}`, "Tiempo medio", "Tiempo medio dentro del umbral"]}
      filas={datos.resolucion_por_gravedad.map(r => [
        gravedadLabels[r.gravedad], r.emergencias, r.resueltas, r.cierres_confirmados, r.resueltas_sin_cierre,
        porcentajeMonitoreo(r.tasa_resolucion), r.cierres_con_tiempo, r.dentro_del_umbral,
        porcentajeMonitoreo(r.tasa_dentro_del_umbral), horasMonitoreo(r.promedio_segundos),
        horasMonitoreo(r.promedio_dentro_del_umbral_segundos),
      ])} />
    {resolucionesConTiempo.length > 0 && <GraficoMetricas titulo={`Resolución en hasta ${limiteResolucion} por gravedad`} unidad="%" datos={resolucionesConTiempo} />}
    <TablaMonitoreo titulo="Reaperturas y reformulaciones" columnas={["Emergencia", "Reaperturas", "Reformulaciones"]}
      filas={datos.reiteradas.map(r => [`#${r.emergencia_id}`, r.reaperturas, r.reformulaciones])} />
    <TablaMonitoreo titulo="ONG por recursos adjudicados y cumplimiento"
      columnas={["ONG", "Capacidad", "Unidad", "Cantidad adjudicada", "Aportes", "Finalizados", "Pendientes", "Finalizados con tiempo medido", `Finalizados en hasta ${limiteAportes}`, `% en hasta ${limiteAportes}`]}
      filas={datos.ranking_ongs.map(r => [
        r.ong, r.capacidad, r.unidad, r.cantidad, r.aportes, r.finalizados, r.aportes - r.finalizados,
        r.finalizados_con_tiempo, r.dentro_del_umbral, porcentajeMonitoreo(r.tasa_dentro_del_umbral),
      ])} />
    <TablaMonitoreo titulo="Cobertura efectiva al cierre" columnas={["Cobertura", "Cierres", "Proporción"]}
      filas={filasCobertura}
      descripcion={cobertura.sin_evidencia ? `${cobertura.sin_evidencia} emergencias resueltas sin evidencia completa de cobertura.` : undefined}
      vacio="Sin cierres con cantidades cumplidas verificables para estos filtros." />
    <TablaMonitoreo titulo="Demanda por rubro" columnas={["Capacidad", "Unidad", "Necesidad publicada"]}
      filas={datos.demanda_rubros.map(r => [r.capacidad, r.unidad, r.cantidad])}
      vacio="Sin necesidades publicadas para los filtros seleccionados." />
    {movilizados && <TablaMonitoreo titulo="Suministros movilizados"
      columnas={["Capacidad", "Unidad", "Cantidad movilizada"]}
      filas={movilizados.cantidades.map(r => [r.capacidad, r.unidad, r.cantidad])}
      descripcion={`${movilizados.participaciones_con_registro} participaciones liberadas con cantidades declaradas · ${movilizados.participaciones_sin_registro} sin registro.`}
      vacio="Sin cantidades movilizadas declaradas para estos filtros." />}
    {consorcios && <article className="rounded-2xl border border-slate-200 bg-white p-5">
      <h3 className="text-lg font-bold text-slate-900">Resolución mediante consorcios</h3>
      <p className="mt-2 text-2xl font-bold text-cyan-800">{porcentajeMonitoreo(consorcios.proporcion)}</p>
      <p className="text-sm text-slate-600">{consorcios.con_consorcio} de {consorcios.con_adjudicacion_verificable} cierres con adjudicación verificable · {consorcios.sin_adjudicacion_verificable} sin evidencia de adjudicación.</p>
    </article>}
    <article className="rounded-2xl border border-slate-200 bg-white p-5">
      <h3 className="text-lg font-bold text-slate-900">De la alerta a la primera adjudicación efectiva</h3>
      <p className="mt-2 text-2xl font-bold text-cyan-800">{horasMonitoreo(datos.alerta_adjudicacion_promedio_segundos)}</p>
      <p className="text-sm text-slate-600">{datos.alerta_adjudicacion_muestras} emergencias con tiempo medido.</p>
    </article>
    <details className="rounded-xl border border-slate-200 bg-white p-4">
      <summary className="cursor-pointer font-semibold text-slate-800">Fórmulas y alcance de los indicadores</summary>
      <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-600">{datos.definiciones.map(d => <li key={d}>{d}</li>)}</ul>
    </details>
  </section>;
}
