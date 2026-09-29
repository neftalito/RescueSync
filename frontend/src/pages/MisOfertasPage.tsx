import { type ReactElement } from "react";
import { Link } from "react-router";

import { ApiError } from "../api/client";
import { useMisOfertas } from "../hooks/useMisOfertas";
import { gravedadLabels } from "../schemas/emergencia";
import { estadoOfertaLabels, tipoAporteLabels, type Oferta } from "../schemas/oferta";

function formatearFecha(iso: string): string {
  return new Date(iso).toLocaleString("es-AR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function TarjetaOferta({ oferta }: { oferta: Oferta }): ReactElement {
  return (
    <details className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-cyan-800">
            {gravedadLabels[oferta.emergencia.gravedad]} · {oferta.emergencia.zona}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Presentada el {formatearFecha(oferta.presentada_en)}
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
          {estadoOfertaLabels[oferta.estado]}
        </span>
      </summary>
      <div className="mt-4 space-y-2 border-t border-slate-100 pt-4 text-sm leading-6 text-slate-600">
        <p>{oferta.emergencia.descripcion}</p>
        {oferta.observaciones && <p>{oferta.observaciones}</p>}
        <ul className="space-y-1">
          {oferta.items.map((item) => (
            <li key={item.id}>
              {item.descripcion} — {item.cantidad_ofrecida} {item.unidad} (
              {tipoAporteLabels[item.tipo]})
            </li>
          ))}
        </ul>
        {oferta.editable && (
          <Link
            to={`/ofertas/${oferta.id}/editar`}
            className="mt-4 inline-flex rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700"
          >
            Modificar oferta
          </Link>
        )}
      </div>
    </details>
  );
}

export function MisOfertasPage(): ReactElement {
  const query = useMisOfertas();

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div>
            <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
              RescueSync
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-950">Mis ofertas</h1>
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
            Cargando tus ofertas…
          </section>
        ) : query.isError ? (
          <section
            role="alert"
            className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm leading-6 text-red-800 shadow-sm"
          >
            <p>
              {query.error instanceof ApiError
                ? query.error.message
                : "No pudimos consultar tus ofertas. Intentá nuevamente."}
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
            Todavía no presentaste ofertas.
          </p>
        ) : (
          <div className="space-y-4">
            {query.data.map((oferta) => (
              <TarjetaOferta key={oferta.id} oferta={oferta} />
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
