import { type ReactElement, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { ApiError } from "../api/client";
import { LotesForm } from "../components/LotesForm";
import { useEmergencias } from "../hooks/useEmergencias";
import { useLotes } from "../hooks/useLotes";
import { estadoLabels, gravedadLabels } from "../schemas/emergencia";
import type { Session } from "../schemas/auth";

interface LotesPageProps {
  session: Session;
}

function formatearFecha(iso: string): string {
  return new Date(iso).toLocaleString("es-AR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function parsearId(valor: string | undefined): number | null {
  if (valor === undefined || !/^\d+$/.test(valor)) return null;
  const id = Number(valor);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

function Aviso({
  tono,
  children,
}: {
  tono: "neutro" | "error";
  children: ReactNode;
}): ReactElement {
  return tono === "error" ? (
    <section
      role="alert"
      className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm leading-6 text-red-800 shadow-sm"
    >
      {children}
    </section>
  ) : (
    <section
      role="status"
      className="rounded-2xl border border-slate-200 bg-white p-6 text-sm leading-6 text-slate-600 shadow-sm"
    >
      {children}
    </section>
  );
}

function ErrorConReintento({
  mensaje,
  onReintentar,
}: {
  mensaje: string;
  onReintentar: () => void;
}): ReactElement {
  return (
    <Aviso tono="error">
      <p>{mensaje}</p>
      <button
        type="button"
        onClick={onReintentar}
        className="mt-4 rounded-xl border border-red-700 bg-white px-4 py-2.5 text-sm font-semibold text-red-900 transition hover:bg-red-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700"
      >
        Reintentar
      </button>
    </Aviso>
  );
}

function SeccionLotes({
  emergenciaId,
  csrfToken,
}: {
  emergenciaId: number;
  csrfToken: string;
}): ReactElement {
  const query = useLotes(emergenciaId);

  if (query.isPending) {
    return <Aviso tono="neutro">Cargando lotes…</Aviso>;
  }

  if (query.isError) {
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
    <LotesForm
      emergenciaId={emergenciaId}
      csrfToken={csrfToken}
      lotes={query.data}
    />
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

  if (query.isPending) {
    return <Aviso tono="neutro">Cargando emergencia…</Aviso>;
  }

  if (query.isError) {
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
  if (emergencia === undefined) {
    return (
      <Aviso tono="neutro">
        La emergencia no está disponible en tu bandeja. Puede que la gestione
        otro centro coordinador o que ya no esté pendiente.
      </Aviso>
    );
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[320px_minmax(0,1fr)] lg:items-start">
      <aside
        aria-labelledby="detalle-emergencia"
        className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        <p className="text-xs font-bold tracking-[0.14em] text-slate-500 uppercase">
          Emergencia N.º {emergencia.id}
        </p>
        <h2
          id="detalle-emergencia"
          className="mt-3 text-lg font-semibold text-slate-950"
        >
          {emergencia.zona}
        </h2>
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
      </aside>

      <SeccionLotes emergenciaId={emergencia.id} csrfToken={csrfToken} />
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
