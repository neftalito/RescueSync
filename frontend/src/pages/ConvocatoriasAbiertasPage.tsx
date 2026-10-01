import { type ReactElement } from "react";
import { Link } from "react-router";

import { ApiError } from "../api/client";
import { useConvocatoriasAbiertas } from "../hooks/useConvocatoriasAbiertas";
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
      <ul className="mt-3 space-y-1 text-sm text-slate-700">
        {convocatoria.lotes.map((lote) => (
          <li key={lote.lote_id}>
            {lote.tipo_necesidad}: {formatearCantidad(lote.cantidad_publicada)}{" "}
            {lote.unidad_publicada}
          </li>
        ))}
      </ul>
      <Link
        to={`/emergencias/${convocatoria.emergencia_id}/lotes`}
        className="mt-4 inline-flex rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700"
      >
        Ver lotes
      </Link>
    </article>
  );
}

export function ConvocatoriasAbiertasPage(): ReactElement {
  const query = useConvocatoriasAbiertas();

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
            className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Volver al inicio
          </Link>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-6">
        {query.isPending ? (
          <section
            role="status"
            className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm"
          >
            Cargando convocatorias…
          </section>
        ) : query.isError ? (
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
              className="mt-4 rounded-xl border border-red-700 bg-white px-4 py-2.5 text-sm font-semibold text-red-900 transition hover:bg-red-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700"
            >
              Reintentar
            </button>
          </section>
        ) : query.data.length === 0 ? (
          <p
            role="status"
            className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm"
          >
            No hay convocatorias abiertas por el momento.
          </p>
        ) : (
          <div className="space-y-4">
            {query.data.map((convocatoria) => (
              <TarjetaConvocatoria
                key={convocatoria.id}
                convocatoria={convocatoria}
              />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
