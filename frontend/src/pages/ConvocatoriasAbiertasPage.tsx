import { type ReactElement } from "react";
import { CampoBusqueda } from "../components/CampoBusqueda";
import { useTextoBusqueda } from "../hooks/useTextoBusqueda";
import { Link } from "react-router";

import { ListadoLocal, ListadoRemoto } from "../components/ListadoProgresivo";
import { ActionIcon } from "../components/ActionIcon";
import { ApiError } from "../api/client";
import { useConvocatoriasPaginadas } from "../hooks/useConvocatoriasAbiertas";
import type { Convocatoria } from "../schemas/convocatoria";
import { gravedadLabels } from "../schemas/emergencia";
import { formatearCantidad } from "../utils/cantidades";

function formatearFecha(iso: string): string {
  return new Date(iso).toLocaleString("es-AR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function TarjetaConvocatoria({
  convocatoria,
}: {
  convocatoria: Convocatoria;
}): ReactElement {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-cyan-800">
            {gravedadLabels[convocatoria.emergencia.gravedad]} ·{" "}
            {convocatoria.emergencia.zona}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Convocatoria N.º {convocatoria.numero}
          </p>
        </div>
        <span className="rounded-full bg-cyan-100 px-3 py-1 text-xs font-semibold text-cyan-900">
          Cierra el {formatearFecha(convocatoria.cierra_en)}
        </span>
      </div>
      <p className="mt-3 leading-6 text-slate-700">
        {convocatoria.emergencia.descripcion}
      </p>
      <p className="mt-3 text-sm text-slate-600">
        {convocatoria.lotes.length === 1
          ? "1 lote publicado"
          : `${convocatoria.lotes.length} lotes publicados`}
      </p>
      <ListadoLocal items={convocatoria.lotes} etiqueta={`Lotes de convocatoria ${convocatoria.id}`} className="mt-3">
        {(visibles) => (
          <ul className="mt-3 space-y-1 text-sm text-slate-700">
            {visibles.map((lote) => (
              <li key={lote.lote_id}>
                {lote.tipo_necesidad}: {formatearCantidad(lote.cantidad_publicada)}{" "}
                {lote.unidad_publicada}
              </li>
            ))}
          </ul>
        )}
      </ListadoLocal>
      <Link
        to={`/emergencias/${convocatoria.emergencia_id}/lotes`}
        className="action-button action-primary mt-4"
      >
        Ver lotes
      </Link>
    </article>
  );
}

export function ConvocatoriasAbiertasPage(): ReactElement {
  const busqueda = useTextoBusqueda();
  const zona = useTextoBusqueda();
  const query = useConvocatoriasPaginadas(busqueda.termino, zona.termino);

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div>
            <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
              RescueSync
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-950">
              Convocatorias abiertas
            </h1>
          </div>
          <Link
            to="/"
            className="action-button action-icon"
            title="Volver al inicio"
          >
            <ActionIcon name="home" />
            <span className="sr-only">Volver al inicio</span>
          </Link>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-6">
        <div className="mb-4 grid gap-4 sm:grid-cols-2">
          <CampoBusqueda etiqueta="Buscar convocatorias" ejemplo="Necesidad, descripción o número" valor={busqueda.texto} cambiar={busqueda.cambiar} />
          <CampoBusqueda etiqueta="Zona" ejemplo="Ej.: Norte" valor={zona.texto} cambiar={zona.cambiar} />
        </div>
        {query.isPending ? (
          <section
            role="status"
            className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm"
          >
            Cargando convocatorias…
          </section>
        ) : query.data === undefined ? (
          <section
            role="alert"
            className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm leading-6 text-red-800 shadow-sm"
          >
            <p>
              {query.error instanceof ApiError
                ? query.error.message
                : "No pudimos consultar las convocatorias. Intentá nuevamente."}
            </p>
            <button
              type="button"
              onClick={() => void query.refetch()}
              className="action-button action-danger action-icon mt-4"
              title="Reintentar"
            >
              <ActionIcon name="refresh" />
              <span className="sr-only">Reintentar</span>
            </button>
          </section>
        ) : query.data.length === 0 ? (
          <p
            role="status"
            className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm"
          >
            {busqueda.termino || zona.termino
              ? "No encontramos convocatorias que coincidan con la búsqueda y los filtros."
              : "No hay convocatorias abiertas por el momento."}
          </p>
        ) : (
          <ListadoRemoto query={query} etiqueta="Convocatorias abiertas">
            <div className="space-y-4">
              {query.data.map((convocatoria) => (
                <TarjetaConvocatoria
                  key={convocatoria.id}
                  convocatoria={convocatoria}
                />
              ))}
            </div>
          </ListadoRemoto>
        )}
      </div>
    </main>
  );
}
