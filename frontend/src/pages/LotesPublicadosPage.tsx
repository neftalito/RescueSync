import { type ReactElement } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client";
import { useLotesPublicados } from "../hooks/useLotes";
import {
  estadoLoteLabels,
  type LotePublicadoPublico,
} from "../schemas/lote";

function parsearId(valor: string | undefined): number | null {
  if (valor === undefined || !/^\d+$/.test(valor)) return null;
  const id = Number(valor);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

function TarjetaLote({ lote }: { lote: LotePublicadoPublico }): ReactElement {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between gap-4">
        <p className="text-sm font-semibold text-cyan-800">
          {lote.tipo_necesidad}
        </p>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
          {estadoLoteLabels[lote.estado]}
        </span>
      </div>
      <p className="mt-2 text-sm text-slate-700">
        {lote.cantidad_requerida} {lote.unidad}
      </p>
      {lote.descripcion && (
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {lote.descripcion}
        </p>
      )}
    </article>
  );
}

function Contenido({ emergenciaId }: { emergenciaId: number | null }): ReactElement {
  if (emergenciaId === null) {
    return (
      <section
        role="alert"
        className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm leading-6 text-red-800 shadow-sm"
      >
        El identificador de emergencia no es válido.
      </section>
    );
  }

  return <ListadoLotes emergenciaId={emergenciaId} />;
}

function ListadoLotes({ emergenciaId }: { emergenciaId: number }): ReactElement {
  const query = useLotesPublicados(emergenciaId);

  if (query.isPending) {
    return (
      <section
        role="status"
        className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm"
      >
        Cargando lotes…
      </section>
    );
  }

  if (query.isError) {
    const mensaje =
      query.error instanceof ApiError
        ? query.error.message
        : "No pudimos consultar los lotes. Intentá nuevamente.";
    return (
      <section
        role="alert"
        className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm leading-6 text-red-800 shadow-sm"
      >
        <p>{mensaje}</p>
        <button
          type="button"
          onClick={() => void query.refetch()}
          className="mt-4 rounded-xl border border-red-700 bg-white px-4 py-2.5 text-sm font-semibold text-red-900 transition hover:bg-red-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700"
        >
          Reintentar
        </button>
      </section>
    );
  }

  if (query.data.length === 0) {
    return (
      <p
        role="status"
        className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm"
      >
        Esta convocatoria todavía no tiene lotes publicados.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {query.data.map((lote) => (
        <TarjetaLote key={lote.id} lote={lote} />
      ))}
    </div>
  );
}

export function LotesPublicadosPage(): ReactElement {
  const { emergenciaId } = useParams();

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div>
            <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
              RescueSync
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-950">
              Lotes publicados
            </h1>
          </div>
          <Link
            to="/convocatorias"
            className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Volver a convocatorias
          </Link>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-6">
        <Contenido emergenciaId={parsearId(emergenciaId)} />
      </div>
    </main>
  );
}
