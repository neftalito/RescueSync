import { type ReactElement } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client";
import {
  Aviso,
  AvisoRefresco,
  ErrorConReintento,
} from "../components/EstadosConsulta";
import { LotesForm } from "../components/LotesForm";
import { PublicarConvocatoria } from "../components/PublicarConvocatoria";
import { useEmergencias } from "../hooks/useEmergencias";
import { useLotes } from "../hooks/useLotes";
import { estadoLabels, gravedadLabels, type Emergencia } from "../schemas/emergencia";
import type { Session } from "../schemas/auth";
import { formatearFecha } from "../utils/fechas";

interface LotesPageProps {
  session: Session;
}

function parsearId(valor: string | undefined): number | null {
  if (valor === undefined || !/^\d+$/.test(valor)) return null;
  const id = Number(valor);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

function SeccionLotes({
  emergenciaId,
  csrfToken,
  publicada,
}: {
  emergenciaId: number;
  csrfToken: string;
  publicada: boolean;
}): ReactElement {
  const query = useLotes(emergenciaId);

  if (query.data === undefined) {
    if (!query.isError) {
      return <Aviso tono="neutro">Cargando lotes…</Aviso>;
    }
    const mensaje =
      query.error instanceof ApiError
        ? query.error.message
        : "No pudimos consultar los lotes. Intentá nuevamente.";
    return (
      <ErrorConReintento
        mensaje={mensaje}
        onReintentar={() => void query.refetch()}
      />
    );
  }

  // El formulario toma los borradores como valores iniciales solo al montarse;
  // después de guardar se sincroniza con la respuesta del POST.
  return (
    <div className="min-w-0 space-y-4">
      {query.isRefetchError && (
        <AvisoRefresco
          mensaje="No pudimos actualizar los lotes."
          onReintentar={() => void query.refetch()}
        />
      )}
      <LotesForm
        emergenciaId={emergenciaId}
        csrfToken={csrfToken}
        lotes={query.data}
      />
      <PublicarConvocatoria
        emergenciaId={emergenciaId}
        csrfToken={csrfToken}
        cantidadBorrador={query.data.filter((lote) => lote.estado === "BORRADOR").length}
        publicada={publicada}
      />
    </div>
  );
}

function DetalleEmergencia({
  emergencia,
  emergenciaId,
}: {
  emergencia: Emergencia | undefined;
  emergenciaId: number;
}): ReactElement {
  return (
    <aside
      aria-labelledby="detalle-emergencia"
      className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <p className="text-xs font-bold tracking-[0.14em] text-slate-500 uppercase">
        Emergencia N.º {emergenciaId}
      </p>
      <h2
        id="detalle-emergencia"
        className="mt-3 text-lg font-semibold text-slate-950"
      >
        {emergencia?.zona ?? "Sin detalle en la bandeja"}
      </h2>
      {emergencia === undefined ? (
        <p role="status" className="mt-4 text-sm leading-6 text-slate-600">
          Esta emergencia ya no está pendiente y por eso no aparece en tu
          bandeja. Sus lotes siguen visibles y editables desde acá.
        </p>
      ) : (
        <dl className="mt-4 space-y-4 text-sm">
          <div>
            <dt className="text-slate-500">Gravedad</dt>
            <dd className="mt-1 font-semibold text-slate-950">
              {gravedadLabels[emergencia.gravedad]}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Estado</dt>
            <dd className="mt-1 font-semibold text-slate-950">
              {estadoLabels[emergencia.estado]}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Registrada</dt>
            <dd className="mt-1 font-semibold text-slate-950">
              {formatearFecha(emergencia.creada_en)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Descripción</dt>
            <dd className="mt-1 leading-6 text-slate-700">
              {emergencia.descripcion}
            </dd>
          </div>
        </dl>
      )}
    </aside>
  );
}

function Contenido({
  emergenciaId,
  csrfToken,
}: {
  emergenciaId: number | null;
  csrfToken: string;
}): ReactElement {
  // La API aún no expone GET /emergencias/{id}: el detalle sale de la bandeja,
  // que el backend ya filtra por el centro del coordinador autenticado.
  const query = useEmergencias();

  if (emergenciaId === null) {
    return <Aviso tono="error">El identificador de emergencia no es válido.</Aviso>;
  }

  if (query.data === undefined) {
    if (!query.isError) {
      return <Aviso tono="neutro">Cargando emergencia…</Aviso>;
    }
    const mensaje =
      query.error instanceof ApiError
        ? query.error.message
        : "No pudimos consultar la emergencia. Intentá nuevamente.";
    return (
      <ErrorConReintento
        mensaje={mensaje}
        onReintentar={() => void query.refetch()}
      />
    );
  }

  const emergencia = query.data.find((item) => item.id === emergenciaId);

  return (
    <div className="space-y-4">
      {query.isRefetchError && (
        <AvisoRefresco
          mensaje="No pudimos actualizar la emergencia."
          onReintentar={() => void query.refetch()}
        />
      )}
      {/* El detalle y la sección de lotes mantienen su posición en el árbol
          aunque la emergencia desaparezca de la bandeja al publicar: si se
          reemplazara una rama por otra, `PublicarConvocatoria` se remontaría y
          perdería el resultado de la publicación que acaba de realizar. */}
      <div className="grid gap-8 lg:grid-cols-[320px_minmax(0,1fr)] lg:items-start">
        <DetalleEmergencia emergencia={emergencia} emergenciaId={emergenciaId} />
        <SeccionLotes
          emergenciaId={emergenciaId}
          csrfToken={csrfToken}
          publicada={emergencia?.estado === "PUBLICADA"}
        />
      </div>
    </div>
  );
}

export function LotesPage({ session }: LotesPageProps): ReactElement {
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
              Generar lotes
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
        <Contenido
          emergenciaId={parsearId(emergenciaId)}
          csrfToken={session.csrf_token}
        />
      </div>
    </main>
  );
}
