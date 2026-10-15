import { ListadoLocal } from "./ListadoProgresivo";
import { zodResolver } from "@hookform/resolvers/zod";
import { useState, type ReactElement } from "react";
import { useForm } from "react-hook-form";
import { ActionIcon } from "./ActionIcon";
import { ApiError } from "../api/client";
import { useMetricas } from "../hooks/useMetricas";
import {
  estados,
  estadoLabels,
  gravedades,
  gravedadLabels,
} from "../schemas/emergencia";
import {
  filtrosInicialesMetricas,
  filtrosMetricasFormSchema,
  type FiltrosMetricasForm,
} from "../schemas/metricas";
import {
  indicadoresPendientes,
  motivoIndicadoresPendientes,
} from "../utils/exportarMetricas";
import { GraficoMetricas } from "./GraficoMetricas";
import { ExportarMetricasMenu } from "./ExportarMetricasMenu";
import { IndicadoresProceso } from "./IndicadoresProceso";
import { ActividadesBonita } from "./ActividadesBonita";
import {
  coloresMetricas,
  etiquetasMetricas as etiquetas,
} from "../utils/coloresMetricas";

const resumenLabels = {
  emergencias: "Emergencias",
  activas: "Activas",
  resueltas: "Resueltas",
  convocatorias_abiertas: "Convocatorias abiertas",
  ofertas_presentadas: "Ofertas presentadas",
  ong_participantes: "ONG participantes",
};
const estiloCampo =
  "mt-1 block w-full min-w-0 rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 focus-visible:outline-cyan-700";

export function DashboardAuditor(): ReactElement {
  const [filtros, setFiltros] = useState(filtrosInicialesMetricas);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FiltrosMetricasForm>({
    resolver: zodResolver(filtrosMetricasFormSchema),
    defaultValues: filtros,
  });
  const { locales, tiempos } = useMetricas(filtros);
  const actualizando = locales.isFetching || tiempos.isFetching;
  const reporte = locales.data;
  const historial = tiempos.isError ? undefined : tiempos.data;
  const exportable = reporte !== undefined && !locales.isError && !actualizando;

  return (
    <section aria-labelledby="dashboard-auditor" className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2
            id="dashboard-auditor"
            className="text-2xl font-bold tracking-tight text-slate-950"
          >
            Panel de indicadores
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Seguimiento global de las emergencias, las ofertas de ayuda y los
            tiempos del proceso.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="action-button action-icon"
            disabled={actualizando}
            onClick={() => {
              void locales.refetch();
              void tiempos.refetch();
            }}
            title={actualizando ? "Actualizando…" : "Actualizar métricas"}
          >
            <ActionIcon name="refresh" />
            <span className="sr-only">
              {actualizando ? "Actualizando…" : "Actualizar métricas"}
            </span>
          </button>
          <ExportarMetricasMenu
            reporte={reporte}
            tiempos={historial}
            habilitado={exportable}
          />
        </div>
      </div>
      <form
        onSubmit={(event) => void handleSubmit(setFiltros)(event)}
        className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-6"
        aria-label="Filtros de indicadores"
      >
        <div className="grid min-w-0 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <label className="min-w-0 text-sm font-semibold text-slate-700">
            Desde
            <input
              type="date"
              {...register("fecha_desde")}
              className={estiloCampo}
              aria-invalid={!!errors.fecha_desde}
              aria-describedby={
                errors.fecha_desde ? "error-fecha-desde" : undefined
              }
            />
          </label>
          <label className="min-w-0 text-sm font-semibold text-slate-700">
            Hasta
            <input
              type="date"
              {...register("fecha_hasta")}
              className={estiloCampo}
              aria-invalid={!!errors.fecha_hasta}
              aria-describedby={
                errors.fecha_hasta ? "error-fecha-hasta" : undefined
              }
            />
          </label>
          <label className="min-w-0 text-sm font-semibold text-slate-700">
            Municipio
            <select {...register("municipio_id")} className={estiloCampo}>
              <option value="">Todos los municipios</option>
              {reporte?.municipios.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.nombre}
                </option>
              ))}
            </select>
          </label>
          <label className="min-w-0 text-sm font-semibold text-slate-700">
            Gravedad
            <select {...register("gravedad")} className={estiloCampo}>
              <option value="">Todas las gravedades</option>
              {gravedades.map((g) => (
                <option key={g} value={g}>
                  {gravedadLabels[g]}
                </option>
              ))}
            </select>
          </label>
          <label className="min-w-0 text-sm font-semibold text-slate-700">
            Estado
            <select {...register("estado")} className={estiloCampo}>
              <option value="">Todos los estados</option>
              {estados.map((e) => (
                <option key={e} value={e}>
                  {estadoLabels[e]}
                </option>
              ))}
            </select>
          </label>
        </div>
        {errors.fecha_desde && (
          <p
            id="error-fecha-desde"
            role="alert"
            className="mt-3 text-sm text-red-700"
          >
            {errors.fecha_desde.message}
          </p>
        )}
        {errors.fecha_hasta && (
          <p
            id="error-fecha-hasta"
            role="alert"
            className="mt-3 text-sm text-red-700"
          >
            {errors.fecha_hasta.message}
          </p>
        )}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-3xl text-xs leading-5 text-slate-500">
            Las fechas filtran el alta de las emergencias en horario de
            Argentina. Los indicadores muestran la situación actual de sus datos
            relacionados.
          </p>
          <button
            className="action-button action-primary"
            type="submit"
          >
            Aplicar filtros
          </button>
        </div>
      </form>
      {locales.isPending && (
        <p role="status" className="rounded-2xl bg-white p-6 text-slate-600">
          Cargando indicadores…
        </p>
      )}
      {locales.isError && (
        <div
          role="alert"
          className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800"
        >
          <p>
            {locales.error instanceof ApiError
              ? locales.error.message
              : "No pudimos cargar las métricas."}
          </p>
          <button
            className="action-button action-icon mt-3"
            onClick={() => void locales.refetch()}
            type="button"
            title="Reintentar métricas"
          >
            <ActionIcon name="refresh" />
            <span className="sr-only">Reintentar métricas</span>
          </button>
        </div>
      )}
      {reporte && !locales.isError && (
        <>
          <p className="text-xs text-slate-500">
            Reporte local actualizado:{" "}
            {new Date(reporte.generado_en).toLocaleString("es-AR", {
              timeZone: "America/Argentina/Buenos_Aires",
            })}{" "}
            (Argentina). Filtros aplicados: {reporte.filtros.fecha_desde} a{" "}
            {reporte.filtros.fecha_hasta} ·{" "}
            {reporte.municipios.find(
              (m) => m.id === reporte.filtros.municipio_id,
            )?.nombre ?? "Todos los municipios"}{" "}
            ·{" "}
            {reporte.filtros.gravedad
              ? gravedadLabels[reporte.filtros.gravedad]
              : "Todas las gravedades"}{" "}
            ·{" "}
            {reporte.filtros.estado
              ? estadoLabels[reporte.filtros.estado]
              : "Todos los estados"}
            .
          </p>
          <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(resumenLabels).map(([clave, titulo]) => (
              <div
                key={clave}
                className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
              >
                <dt className="text-sm font-medium text-slate-500">{titulo}</dt>
                <dd
                  className={`mt-2 text-3xl font-bold tabular-nums ${clave === "resueltas" ? "text-green-700" : clave === "activas" ? "text-orange-700" : "text-slate-950"}`}
                >
                  {reporte.resumen[
                    clave as keyof typeof resumenLabels
                  ].toLocaleString("es-AR")}
                </dd>
              </div>
            ))}
          </dl>
          {reporte.resumen.emergencias === 0 && (
            <p
              role="status"
              className="rounded-xl border border-cyan-200 bg-cyan-50 p-4 text-sm text-cyan-900"
            >
              No hay emergencias para los filtros seleccionados.
            </p>
          )}
          <div className="grid min-w-0 gap-5 lg:grid-cols-2">
            <GraficoMetricas
              titulo="Evolución mensual de altas"
              tipo="lineas"
              datos={reporte.evolucion_mensual.map((d) => ({
                nombre: d.categoria,
                valor: d.cantidad,
              }))}
            />
            <GraficoMetricas
              titulo="Emergencias por estado"
              datos={reporte.por_estado.map((d) => ({
                nombre: etiquetas[d.categoria] ?? d.categoria,
                color: coloresMetricas[d.categoria],
                valor: d.cantidad,
              }))}
            />
            <GraficoMetricas
              titulo="Emergencias por gravedad"
              tipo="torta"
              datos={reporte.por_gravedad.map((d) => ({
                nombre: etiquetas[d.categoria] ?? d.categoria,
                color: coloresMetricas[d.categoria],
                valor: d.cantidad,
              }))}
            />
            <GraficoMetricas
              titulo="Ofertas individuales y conjuntas"
              tipo="torta"
              datos={reporte.tipos_oferta.map((d) => ({
                nombre: etiquetas[d.categoria] ?? d.categoria,
                color: coloresMetricas[d.categoria],
                valor: d.cantidad,
              }))}
            />
          </div>
          <article className="rounded-2xl border border-slate-200 bg-white p-4 sm:p-6">
            <h3 className="text-lg font-bold text-slate-900">
              Cantidades ofrecidas por capacidad
            </h3>
            <p className="mt-2 text-sm text-slate-500">
              Suma de las versiones vigentes presentadas. Cada capacidad y
              unidad se informa por separado; estas cantidades representan
              ofrecimientos.
            </p>
            {reporte.cantidades_ofrecidas.length === 0 ? (
              <p className="mt-4 text-sm text-slate-500">
                No hay cantidades ofrecidas para estos filtros.
              </p>
            ) : (
              <ListadoLocal items={reporte.cantidades_ofrecidas} etiqueta="Cantidades ofrecidas por capacidad" className="mt-3">
                {(visibles) => (
                  <table className="w-full text-left text-sm">
                    <caption className="sr-only">Cantidades ofrecidas</caption>
                    <thead className="sticky top-0 bg-white">
                      <tr>
                        <th className="py-3">Capacidad</th>
                        <th className="px-3 py-3 text-right">Cantidad</th>
                        <th className="py-3">Unidad</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibles.map((c) => (
                        <tr
                          key={`${c.capacidad}-${c.unidad}`}
                          className="border-t border-slate-100"
                        >
                          <td className="py-3 pr-2">{c.capacidad}</td>
                          <td className="px-3 py-3 text-right tabular-nums">
                            {Number(c.cantidad).toLocaleString("es-AR", {
                              maximumFractionDigits: 3,
                            })}
                          </td>
                          <td className="py-3">{c.unidad}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </ListadoLocal>
            )}
          </article>
        </>
      )}
      {reporte && !locales.isError && reporte.indicadores_proceso && <IndicadoresProceso datos={reporte.indicadores_proceso} />}
      <section aria-labelledby="tiempos-bonita" className="space-y-4">
        <div>
          <h3 id="tiempos-bonita" className="text-xl font-bold text-slate-900">
            Tiempos por tarea de Bonita
          </h3>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Desde la primera transición registrada hasta completar cada tarea.
            Cada repetición cuenta como una muestra; las tareas incompletas se
            excluyen.
          </p>
        </div>
        {tiempos.isFetching && (
          <p role="status" className="text-sm text-slate-500">
            Consultando historial de Bonita…
          </p>
        )}
        {tiempos.isError && (
          <div
            role="alert"
            className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
          >
            <p>
              No pudimos consultar los tiempos de Bonita. Las métricas locales
              siguen disponibles.
            </p>
            <button
              type="button"
              className="action-button action-icon mt-3"
              onClick={() => void tiempos.refetch()}
              title="Reintentar tiempos"
            >
              <ActionIcon name="refresh" />
              <span className="sr-only">Reintentar tiempos</span>
            </button>
          </div>
        )}
        {historial && (
          <>
            <ActividadesBonita datos={historial} />
            <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-600">
              <p className="font-semibold text-slate-900">
                {historial.disponibilidad === "DISPONIBLE"
                  ? "Historial disponible"
                  : historial.disponibilidad === "PARCIAL"
                    ? "Historial parcial"
                    : historial.disponibilidad === "SIN_DATOS"
                      ? "Sin muestras suficientes de Bonita"
                      : "Historial de Bonita no disponible"}
              </p>
              <p>
                {historial.casos_consultados} de {historial.casos_vinculados}{" "}
                casos vinculados consultados · {historial.casos_con_muestras}{" "}
                con muestras · {historial.casos_sin_historial_suficiente} sin
                historial suficiente · {historial.casos_con_error} sin consulta
                completa · {historial.muestras_descartadas} muestras
                descartadas.
              </p>
              <p className="mt-1 text-xs">
                Actualizado:{" "}
                {new Date(historial.generado_en).toLocaleString("es-AR", {
                  timeZone: "America/Argentina/Buenos_Aires",
                })}{" "}
                (Argentina).
              </p>
            </div>
            {historial.etapas.length > 0 && (
              <>
                <GraficoMetricas
                  titulo="Duración promedio por tarea y versión"
                  unidad="Horas"
                  datos={historial.etapas.map((e) => ({
                    nombre: `${e.etapa} (v${e.version_proceso})`,
                    valor: e.promedio_segundos / 3600,
                  }))}
                />
                <ListadoLocal items={historial.etapas} etiqueta="Promedios y muestras de Bonita" className="mt-3">
                  {(visibles) => (
                    <table className="w-full text-left text-sm">
                      <caption className="mb-3 text-left font-bold text-slate-900">
                        Promedios y muestras de Bonita
                      </caption>
                      <thead className="sticky top-0 bg-white">
                        <tr>
                          <th className="py-2">Tarea</th>
                          <th className="px-3 py-2">Versión</th>
                          <th className="px-3 py-2 text-right">
                            Promedio (horas)
                          </th>
                          <th className="py-2 text-right">Muestras</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibles.map((e) => (
                          <tr
                            key={`${e.etapa}-${e.version_proceso}`}
                            className="border-t border-slate-100"
                          >
                            <td className="py-3">{e.etapa}</td>
                            <td className="px-3 py-3">{e.version_proceso}</td>
                            <td className="px-3 py-3 text-right">
                              {(e.promedio_segundos / 3600).toLocaleString(
                                "es-AR",
                                { maximumFractionDigits: 3 },
                              )}
                            </td>
                            <td className="py-3 text-right">{e.muestras}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </ListadoLocal>
              </>
            )}
          </>
        )}
      </section>
      <div className="grid gap-4 sm:grid-cols-2">
        {indicadoresPendientes.map((titulo) => (
          <article
            key={titulo}
            className="rounded-2xl border border-dashed border-slate-300 bg-slate-100/60 p-5"
          >
            <h3 className="font-semibold text-slate-700">{titulo}</h3>
            <p className="mt-2 text-sm text-slate-500">
              {motivoIndicadoresPendientes}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
