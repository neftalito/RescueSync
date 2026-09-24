import { type ReactElement } from "react";

import { ApiError } from "../api/client";
import { useEmergencias } from "../hooks/useEmergencias";
import {
  estadoLabels,
  gravedadLabels,
  type Emergencia,
} from "../schemas/emergencia";
import type { Role } from "../schemas/auth";

interface BandejaEmergenciasProps {
  rol: Role;
}

const copyPorRol: Record<Role, { titulo: string; vacio: string }> = {
  OPERADOR_MUNICIPAL: {
    titulo: "Mis emergencias",
    vacio: "Todavía no registraste emergencias.",
  },
  COORDINADOR_REGIONAL: {
    titulo: "Emergencias pendientes",
    vacio: "No hay emergencias registradas pendientes.",
  },
  REPRESENTANTE_ONG: {
    titulo: "Emergencias",
    vacio: "No hay emergencias para mostrar.",
  },
  AUDITOR_DIRECTIVO: {
    titulo: "Emergencias",
    vacio: "No hay emergencias para mostrar.",
  },
};

function formatearFecha(iso: string): string {
  return new Date(iso).toLocaleString("es-AR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function TarjetaEmergencia({ emergencia }: { emergencia: Emergencia }): ReactElement {
  return (
    <details className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-cyan-800">
            {gravedadLabels[emergencia.gravedad]} · {emergencia.zona}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Registrada el {formatearFecha(emergencia.creada_en)}
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
          {estadoLabels[emergencia.estado]}
        </span>
      </summary>
      <div className="mt-4 border-t border-slate-100 pt-4 text-sm leading-6 text-slate-600">
        <p>{emergencia.descripcion}</p>
      </div>
    </details>
  );
}

export function BandejaEmergencias({ rol }: BandejaEmergenciasProps): ReactElement {
  const query = useEmergencias();
  const copy = copyPorRol[rol];

  if (query.isPending) {
    return (
      <section
        role="status"
        className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm"
      >
        Cargando emergencias…
      </section>
    );
  }

  if (query.isError) {
    const mensaje =
      query.error instanceof ApiError
        ? query.error.message
        : "No pudimos consultar las emergencias. Intentá nuevamente.";
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

  return (
    <section aria-labelledby="bandeja-emergencias-titulo">
      <h3
        id="bandeja-emergencias-titulo"
        className="text-lg font-semibold text-slate-950"
      >
        {copy.titulo}
      </h3>

      {query.data.length === 0 ? (
        <p
          role="status"
          className="mt-4 rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm"
        >
          {copy.vacio}
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          {query.data.map((emergencia) => (
            <TarjetaEmergencia key={emergencia.id} emergencia={emergencia} />
          ))}
        </div>
      )}
    </section>
  );
}
