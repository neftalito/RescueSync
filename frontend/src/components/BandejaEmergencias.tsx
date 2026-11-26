import { type ReactElement } from "react";
import { Link } from "react-router";

import { ActionIcon } from "./ActionIcon";
import { CampoBusqueda } from "./CampoBusqueda";
import { ApiError } from "../api/client";
import { ListadoRemoto } from "./ListadoProgresivo";
import { useEmergenciasPaginadas } from "../hooks/useEmergencias";
import { useReintentarVinculacionBonita } from "../hooks/useReintentarVinculacionBonita";
import { useTextoBusqueda } from "../hooks/useTextoBusqueda";
import {
  estadoSincronizacionBonitaLabels,
  estadoLabels,
  gravedadLabels,
  type EmergenciaEnBandeja,
  type Estado,
} from "../schemas/emergencia";
import type { Role } from "../schemas/auth";

type RolConBandeja = Extract<
  Role,
  "OPERADOR_MUNICIPAL" | "COORDINADOR_REGIONAL"
>;

interface BandejaEmergenciasProps {
  rol: RolConBandeja;
  csrfToken?: string;
  vista?: "pendientes" | "con-lotes";
  estado?: Estado;
}

const copyPorRol: Record<RolConBandeja, { titulo: string; vacio: string; }> = {
  OPERADOR_MUNICIPAL: {
    titulo: "Mis emergencias",
    vacio: "Todavía no registraste emergencias.",
  },
  COORDINADOR_REGIONAL: {
    titulo: "Emergencias pendientes",
    vacio: "No hay emergencias pendientes sin lotes.",
  },
};

function formatearFecha(iso: string): string {
  return new Date(iso).toLocaleString("es-AR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function TarjetaEmergencia({
  emergencia,
  rol,
  csrfToken,
}: {
  emergencia: EmergenciaEnBandeja;
  rol: RolConBandeja;
  csrfToken?: string;
}): ReactElement {
  const reintento = useReintentarVinculacionBonita();
  const reintentoError =
    reintento.error instanceof ApiError
      ? reintento.error.message
      : reintento.isError
        ? "No pudimos reintentar la vinculación. Intentá nuevamente."
        : null;

  return (
    <details className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
        <div className="min-w-0 break-words">
          <p className="text-sm font-semibold text-cyan-800">
            {gravedadLabels[emergencia.gravedad]} · {emergencia.zona}
          </p>
          <p className="mt-1 text-xs font-medium text-slate-500">Emergencia #{emergencia.id}</p>
          <p className="mt-1 text-xs text-slate-500">
            Registrada el {formatearFecha(emergencia.creada_en)}
          </p>
        </div>
        <span className="shrink-0 rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
          {estadoLabels[emergencia.estado]}
        </span>
      </summary>
      <div className="mt-4 border-t border-slate-100 pt-4 text-sm leading-6 text-slate-600">
        <p>{emergencia.descripcion}</p>
        {rol === "OPERADOR_MUNICIPAL" && (
          <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
            <p className="font-semibold text-slate-800">
              {estadoSincronizacionBonitaLabels[emergencia.bonita_sync]}
            </p>
            {emergencia.bonita_ultimo_error && (
              <p className="mt-1 text-red-800">
                {emergencia.bonita_ultimo_error}
              </p>
            )}
            {reintentoError && (
              <p role="alert" className="mt-2 text-red-800">
                {reintentoError}
              </p>
            )}
            {emergencia.bonita_sync !== "VINCULADA" && csrfToken && (
              <button
                type="button"
                disabled={reintento.isPending}
                onClick={() =>
                  reintento.mutate({ emergenciaId: emergencia.id, csrfToken })
                }
                className="action-button action-primary mt-3"
              >
                {reintento.isPending ? "Vinculando…" : "Vincular con Bonita"}
              </button>
            )}
          </div>
        )}
        {["EN_EVALUACION", "EN_EJECUCION", "RESUELTA"].includes(emergencia.estado) && <Link to={`/emergencias/${emergencia.id}/ejecucion`} className="action-button mt-4 mr-2">Evaluación y ejecución</Link>}
        {rol === "COORDINADOR_REGIONAL" && (
          <Link
            to={`/emergencias/${emergencia.id}/lotes`}
            className="action-button action-primary mt-4"
          >
            {emergencia.tiene_lotes ? "Ver lotes" : "Generar lotes"}
          </Link>
        )}
      </div>
    </details>
  );
}

export function BandejaEmergencias({
  rol,
  csrfToken,
  vista = "pendientes",
  estado,
}: BandejaEmergenciasProps): ReactElement {
  const busqueda = useTextoBusqueda();
  const query = useEmergenciasPaginadas(
    rol === "COORDINADOR_REGIONAL" ? vista === "con-lotes" : undefined,
    estado,
    busqueda.termino,
  );
  const copy =
    rol === "COORDINADOR_REGIONAL" && vista === "con-lotes"
      ? {
        titulo: "Emergencias con lotes",
        vacio: estado
          ? "No hay emergencias con lotes en el estado seleccionado."
          : "Todavía no hay emergencias con lotes creados.",
      }
      : copyPorRol[rol];

  const emergencias =
    rol === "COORDINADOR_REGIONAL"
      ? query.data?.filter(
        (emergencia) =>
          emergencia.tiene_lotes === (vista === "con-lotes") &&
          (estado === undefined || emergencia.estado === estado),
      )
      : query.data;

  return (
    <section aria-labelledby="bandeja-emergencias-titulo">
      <h2
        id="bandeja-emergencias-titulo"
        className="text-lg font-semibold text-slate-950"
      >
        {copy.titulo}
      </h2>
      <div className="mt-4 max-w-md">
        <CampoBusqueda etiqueta="Buscar emergencias" ejemplo="Número o descripción" valor={busqueda.texto} cambiar={busqueda.cambiar} />
      </div>
      {query.isPending ? (
        <p
          role="status"
          className="mt-4 rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm"
        >
          Cargando emergencias…
        </p>
      ) : emergencias === undefined ? (
        <section
          role="alert"
          className="mt-4 rounded-2xl border border-red-200 bg-red-50 p-6 text-sm leading-6 text-red-800 shadow-sm"
        >
          <p>{query.error instanceof ApiError
            ? query.error.message
            : "No pudimos consultar las emergencias. Intentá nuevamente."}</p>
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
      ) : emergencias.length === 0 ? (
        <p
          role="status"
          className="mt-4 rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm"
        >
          {busqueda.termino ? "No encontramos emergencias que coincidan con la búsqueda." : copy.vacio}
        </p>
      ) : (
        <ListadoRemoto query={query} etiqueta={`Listado de ${copy.titulo.toLowerCase()}`} className="mt-4">
          <div className="space-y-3">
            {emergencias.map((emergencia) => (
              <TarjetaEmergencia
                key={emergencia.id}
                emergencia={emergencia}
                rol={rol}
                csrfToken={csrfToken}
              />
            ))}
          </div>
        </ListadoRemoto>
      )}
    </section>
  );
}
