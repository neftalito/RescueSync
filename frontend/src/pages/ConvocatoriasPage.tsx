import type { UseQueryResult } from "@tanstack/react-query";
import { useState, type ReactElement } from "react";
import { Link } from "react-router";

import { ApiError } from "../api/client";
import {
  Aviso,
  AvisoRefresco,
  ErrorConReintento,
} from "../components/EstadosConsulta";
import { useConvocatorias } from "../hooks/useConvocatorias";
import {
  estadoConvocatoriaLabels,
  estadosConvocatoria,
  type ConvocatoriaResumen,
  type EstadoConvocatoria,
} from "../schemas/convocatoria";
import { gravedadLabels } from "../schemas/emergencia";
import { formatearFecha } from "../utils/fechas";

function esEstado(valor: string): valor is EstadoConvocatoria {
  return (estadosConvocatoria as readonly string[]).includes(valor);
}

function FilaConvocatoria({
  convocatoria,
}: {
  convocatoria: ConvocatoriaResumen;
}): ReactElement {
  return (
    <li className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-bold tracking-[0.14em] text-slate-500 uppercase">
            Emergencia N.º {convocatoria.emergencia_id}
          </p>
          <h3 className="mt-2 text-lg font-semibold text-slate-950">
            Convocatoria N.º {convocatoria.numero}
          </h3>
          <p className="mt-1 text-sm text-slate-600">
            {convocatoria.zona} · Gravedad {gravedadLabels[convocatoria.gravedad]}
          </p>
        </div>
        <span className="rounded-full bg-slate-200 px-3 py-1 text-xs font-semibold text-slate-700">
          {estadoConvocatoriaLabels[convocatoria.estado]}
        </span>
      </div>

      <dl className="mt-4 grid gap-4 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-slate-500">Publicada</dt>
          <dd className="mt-1 font-semibold text-slate-950">
            {formatearFecha(convocatoria.publicada_en)}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Cierra</dt>
          <dd className="mt-1 font-semibold text-slate-950">
            {formatearFecha(convocatoria.cierra_en)}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Lotes publicados</dt>
          <dd className="mt-1 font-semibold text-slate-950">
            {convocatoria.cantidad_lotes}
          </dd>
        </div>
      </dl>

      <Link
        to={`/emergencias/${convocatoria.emergencia_id}/lotes`}
        className="mt-5 inline-flex rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700"
      >
        Ver lotes de la emergencia
      </Link>
    </li>
  );
}

function Listado({
  consulta,
  filtro,
}: {
  consulta: UseQueryResult<ConvocatoriaResumen[], Error>;
  filtro: EstadoConvocatoria | undefined;
}): ReactElement {
  if (consulta.data === undefined) {
    if (!consulta.isError) {
      return <Aviso tono="neutro">Cargando convocatorias…</Aviso>;
    }
    const mensaje =
      consulta.error instanceof ApiError
        ? consulta.error.message
        : "No pudimos consultar las convocatorias. Intentá nuevamente.";
    return (
      <ErrorConReintento
        mensaje={mensaje}
        onReintentar={() => void consulta.refetch()}
      />
    );
  }

  if (consulta.data.length === 0) {
    return (
      <Aviso tono="neutro">
        {filtro === undefined
          ? "Todavía no publicaste ninguna convocatoria. Generá los lotes de una emergencia pendiente y publicala para que las ONGs puedan ofertar."
          : `No tenés convocatorias en estado ${estadoConvocatoriaLabels[filtro]}.`}
      </Aviso>
    );
  }

  return (
    <div className="space-y-4">
      {consulta.isRefetchError && (
        <AvisoRefresco
          mensaje="No pudimos actualizar las convocatorias."
          onReintentar={() => void consulta.refetch()}
        />
      )}
      <ul className="space-y-4">
        {consulta.data.map((convocatoria) => (
          <FilaConvocatoria key={convocatoria.id} convocatoria={convocatoria} />
        ))}
      </ul>
    </div>
  );
}

export function ConvocatoriasPage(): ReactElement {
  const [filtro, setFiltro] = useState<EstadoConvocatoria | undefined>(undefined);
  const consulta = useConvocatorias(filtro);

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div>
            <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
              RescueSync
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-950">
              Convocatorias
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
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-xl font-semibold text-slate-950">
            Convocatorias de tu centro
          </h2>
          <p className="mt-2 leading-7 text-slate-600">
            Cada convocatoria publica los lotes de una emergencia y abre una
            ventana para que las ONGs presenten ofertas.
          </p>

          <div className="mt-5 max-w-xs">
            <label
              htmlFor="filtro-estado"
              className="block text-sm font-semibold text-slate-800"
            >
              Estado
            </label>
            <select
              id="filtro-estado"
              value={filtro ?? ""}
              onChange={(event) => {
                const valor = event.target.value;
                setFiltro(esEstado(valor) ? valor : undefined);
              }}
              className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-base shadow-sm outline-none transition focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100"
            >
              <option value="">Todas</option>
              {estadosConvocatoria.map((valor) => (
                <option key={valor} value={valor}>
                  {estadoConvocatoriaLabels[valor]}
                </option>
              ))}
            </select>
          </div>
        </section>

        <section className="mt-8" aria-labelledby="listado-convocatorias">
          <h2 id="listado-convocatorias" className="sr-only">
            Listado de convocatorias
          </h2>
          <Listado consulta={consulta} filtro={filtro} />
        </section>
      </div>
    </main>
  );
}
