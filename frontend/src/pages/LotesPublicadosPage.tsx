import { useId, type ReactElement } from "react";
import { Link, useParams } from "react-router";

import { ListadoRemoto } from "../components/ListadoProgresivo";
import { ActionIcon } from "../components/ActionIcon";
import { ApiError } from "../api/client";
import { useLotesPublicadosPaginados } from "../hooks/useLotes";
import { useConvocatoriasAbiertas } from "../hooks/useConvocatoriasAbiertas";
import { useMisOfertas } from "../hooks/useMisOfertas";
import {
  estadoLoteLabels,
  type LotePublicadoPublico,
} from "../schemas/lote";
import { formatearCantidad } from "../utils/cantidades";

function parsearId(valor: string | undefined): number | null {
  if (valor === undefined || !/^\d+$/.test(valor)) return null;
  const id = Number(valor);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

function TarjetaLote({ lote, motivoBloqueo }: {
  lote: LotePublicadoPublico;
  motivoBloqueo?: string;
}): ReactElement {
  const motivoId = useId();
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
        {formatearCantidad(lote.cantidad_requerida)} {lote.unidad}
      </p>
      {lote.descripcion && (
        <p className="mt-2 text-sm leading-6 text-slate-600">
          {lote.descripcion}
        </p>
      )}
      {motivoBloqueo ? <>
        <button
          type="button"
          disabled
          aria-label={`Crear oferta para ${lote.tipo_necesidad}`}
          aria-describedby={motivoId}
          className="action-button action-primary mt-4"
        >
          Crear oferta
        </button>
        <p id={motivoId} className="mt-2 text-sm leading-6 text-slate-600">{motivoBloqueo}</p>
      </> : (
        <Link
          to={`/ofertas/nueva?loteId=${lote.id}`}
          aria-label={`Crear oferta para ${lote.tipo_necesidad}`}
          className="action-button action-primary mt-4"
        >
          Crear oferta
        </Link>
      )}
    </article>
  );
}

function Contenido({ emergenciaId }: { emergenciaId: number | null; }): ReactElement {
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

function ListadoLotes({ emergenciaId }: { emergenciaId: number; }): ReactElement {
  const query = useLotesPublicadosPaginados(emergenciaId);
  const ofertasQuery = useMisOfertas();
  const convocatoriasQuery = useConvocatoriasAbiertas();
  const verificando = ofertasQuery.isPending || ofertasQuery.isFetching
    || convocatoriasQuery.isPending || convocatoriasQuery.isFetching;
  const errorVerificacion = ofertasQuery.isError || convocatoriasQuery.isError;

  function motivoCreacionBloqueada(lote: LotePublicadoPublico): string | undefined {
    if (verificando) return "Verificando las ofertas de tu ONG en esta convocatoria…";
    if (errorVerificacion) return "No pudimos verificar si tu ONG ya tiene una oferta. Reintentá la verificación antes de crear otra.";

    const convocatoria = convocatoriasQuery.data?.find((opcion) =>
      opcion.emergencia_id === emergenciaId && opcion.lotes.some((item) => item.lote_id === lote.id),
    );
    if (!convocatoria) return "Este lote ya no está disponible en una convocatoria abierta.";

    const ofertas = ofertasQuery.data?.filter((oferta) => oferta.convocatoria_id === convocatoria.id) ?? [];
    if (ofertas.some((oferta) => oferta.items.some((item) => item.lote_id === lote.id))) {
      return "Tu ONG ya creó una oferta para este lote en esta convocatoria. Podés consultarla en Mis ofertas.";
    }
    if (ofertas.length > 0) {
      return "Tu ONG ya tiene una oferta en esta convocatoria. Para agregar este lote, modificá la oferta existente desde Mis ofertas.";
    }
    return undefined;
  }

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

  if (query.data === undefined) {
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
          className="action-button action-danger action-icon mt-4"
          title="Reintentar"
        >
          <ActionIcon name="refresh" />
          <span className="sr-only">Reintentar</span>
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

  return <>
    {errorVerificacion && !verificando && <section
      role="alert"
      className="mb-4 rounded-2xl border border-red-200 bg-white p-5 text-sm text-red-800"
    >
      <p>No pudimos verificar las ofertas de tu ONG en esta convocatoria.</p>
      <button
        type="button"
        onClick={() => {
          void ofertasQuery.refetch();
          void convocatoriasQuery.refetch();
        }}
        className="action-button action-danger mt-3"
      >Reintentar verificación</button>
    </section>}
    <ListadoRemoto query={query} etiqueta="Lotes publicados">
      <div className="space-y-4">
        {query.data.map((lote) => (
          <TarjetaLote key={lote.id} lote={lote} motivoBloqueo={motivoCreacionBloqueada(lote)} />
        ))}
      </div>
    </ListadoRemoto>
  </>;
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
            className="action-button action-icon"
            title="Volver a convocatorias"
          >
            <ActionIcon name="back" />
            <span className="sr-only">Volver a convocatorias</span>
          </Link>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-6">
        <Contenido emergenciaId={parsearId(emergenciaId)} />
      </div>
    </main>
  );
}
