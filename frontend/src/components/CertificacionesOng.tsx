import { ListadoLocal } from "./ListadoProgresivo";
import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { ActionIcon } from "./ActionIcon";
import { ApiError } from "../api/client";
import type {
  Certificacion,
  CertificacionesOng,
} from "../schemas/certificaciones";

const tarjeta =
  "min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm [overflow-wrap:anywhere] sm:p-6";
const vacio =
  "mt-5 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 text-sm leading-6 text-slate-600";
const riesgos = { BAJA: "Bajo", MEDIA: "Medio", ALTA: "Alto", CRITICA: "Crítico" };
const estadosInstitucionales = {
  HABILITADA: {
    nombre: "Habilitada",
    clase: "bg-emerald-50 text-emerald-800 ring-emerald-200",
    descripcion:
      "Tu ONG está habilitada institucionalmente. Las tareas que puede realizar dependen de sus capacidades vigentes.",
  },
  PENDIENTE: {
    nombre: "Pendiente de revisión",
    clase: "bg-amber-50 text-amber-900 ring-amber-200",
    descripcion:
      "La habilitación institucional está pendiente de revisión. Las acreditaciones registradas se conservan en el historial.",
  },
  SUSPENDIDA: {
    nombre: "Suspendida",
    clase: "bg-rose-50 text-rose-800 ring-rose-200",
    descripcion: "La habilitación institucional de tu ONG está suspendida.",
  },
  BAJA: {
    nombre: "Dada de baja",
    clase: "bg-slate-100 text-slate-700 ring-slate-300",
    descripcion: "Tu ONG está dada de baja en el Sistema Nacional.",
  },
};
const estadosVigencia = {
  FUTURA: { nombre: "Futura", clase: "bg-sky-50 text-sky-800 ring-sky-200" },
  VIGENTE: {
    nombre: "Vigente",
    clase: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  },
  VENCIDA: { nombre: "Vencida", clase: "bg-amber-50 text-amber-900 ring-amber-200" },
  REVOCADA: { nombre: "Revocada", clase: "bg-rose-50 text-rose-800 ring-rose-200" },
};
const fecha = (valor: string): string =>
  new Date(valor).toLocaleString("es-AR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
type Perfil = UseQueryResult<CertificacionesOng>;

function ErrorConsulta({ error }: { error: unknown; }): ReactElement {
  return (
    <p
      role="alert"
      className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm leading-6 text-rose-900"
    >
      {error instanceof ApiError
        ? error.message
        : "No pudimos consultar las certificaciones."}
    </p>
  );
}

function EstadoInstitucional({ perfil }: { perfil: Perfil; }): ReactElement {
  const datos = perfil.data;
  const estado = datos ? estadosInstitucionales[datos.estadoOng] : null;
  return (
    <section aria-labelledby="estado-institucional" className={tarjeta}>
      <h3 id="estado-institucional" className="text-lg font-bold text-slate-950">
        Estado institucional
      </h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        La situación de tu organización en el Sistema Nacional.
      </p>
      {perfil.isError ? (
        <ErrorConsulta error={perfil.error} />
      ) : !datos || !estado ? (
        <p role="status" className="mt-5 text-sm text-slate-600">Consultando estado institucional…</p>
      ) : (
        <>
          <span
            className={`mt-5 inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-bold ring-1 ring-inset ${estado.clase}`}
          >
            <span aria-hidden="true" className="size-2 shrink-0 rounded-full bg-current" />
            {estado.nombre}
          </span>
          <p className="mt-4 text-sm leading-6 text-slate-700">{estado.descripcion}</p>
          {datos.motivosInstitucionales.map((motivo) => (
            <p key={motivo.codigo} className="mt-3 rounded-xl bg-amber-50 p-3 text-sm leading-6 text-amber-900">
              {motivo.mensaje}
            </p>
          ))}
          <div className="mt-5 border-t border-slate-100 pt-4 text-xs leading-5 text-slate-500">
            <p>
              Última evaluación:{" "}
              <time dateTime={datos.evaluadoEn}>{fecha(datos.evaluadoEn)}</time>
            </p>
            <p className="mt-1">Se actualiza automáticamente cada minuto.</p>
          </div>
        </>
      )}
    </section>
  );
}

function CapacidadesHabilitadas({ perfil }: { perfil: Perfil; }): ReactElement {
  const datos = perfil.data;
  return (
    <section aria-labelledby="capacidades-habilitadas" className={tarjeta}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 id="capacidades-habilitadas" className="text-lg font-bold text-slate-950">
          Capacidades habilitadas
        </h3>
        {!perfil.isError && datos && (
          <span className="rounded-full bg-cyan-50 px-3 py-1 text-xs font-bold text-cyan-800">
            {datos.capacidadesHabilitadas.length}{" "}
            {datos.capacidadesHabilitadas.length === 1 ? "capacidad" : "capacidades"}
          </span>
        )}
      </div>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        Qué puede aportar tu ONG y hasta qué nivel de riesgo, según sus acreditaciones vigentes.
      </p>
      {perfil.isError ? (
        <p className={vacio}>Las capacidades estarán disponibles cuando se pueda consultar el estado institucional.</p>
      ) : !datos ? (
        <p role="status" className="mt-5 text-sm text-slate-600">Consultando capacidades…</p>
      ) : datos.capacidadesHabilitadas.length === 0 ? (
        <p className={vacio}>Tu ONG no tiene capacidades habilitadas en esta evaluación.</p>
      ) : (
        <ListadoLocal items={datos.capacidadesHabilitadas} etiqueta="Desplazamiento de capacidades habilitadas" className="mt-5">
          {(visibles) => (
            <ul
              aria-label="Listado de capacidades habilitadas"
              className={`grid gap-3 ${datos.capacidadesHabilitadas.length > 1 ? "sm:grid-cols-2" : ""}`}
            >
              {visibles.map((capacidad) => (
                <li key={capacidad.capacidadId} className="min-w-0 rounded-xl border border-cyan-100 bg-cyan-50/50 p-4">
                  <h4 className="font-bold text-slate-950">{capacidad.nombre}</h4>
                  <p className="mt-1 text-xs text-slate-500">Unidad: {capacidad.unidad}</p>
                  <p className="mt-4 text-sm font-semibold text-cyan-900">
                    Riesgo máximo: {riesgos[capacidad.riesgoMaximo]}
                  </p>
                  <p className="mt-3 text-xs font-semibold text-slate-600">Niveles permitidos</p>
                  <ul aria-label={`Niveles permitidos para ${capacidad.nombre}`} className="mt-2 flex flex-wrap gap-2">
                    {capacidad.nivelesRiesgoPermitidos.map((nivel) => (
                      <li
                        key={nivel}
                        className="rounded-lg border border-cyan-200 bg-white px-2.5 py-1 text-xs font-semibold text-cyan-900"
                      >
                        {riesgos[nivel]}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </ListadoLocal>
      )}
      <p className="mt-4 text-xs leading-5 text-slate-500">Esta consulta no reserva recursos.</p>
    </section>
  );
}

function AlcancesCertificacion({
  alcances,
}: {
  alcances: Certificacion["alcances"];
}): ReactElement {
  return alcances.length === 0 ? (
    <p className="text-sm text-slate-500">Esta certificación no tiene capacidades asociadas.</p>
  ) : (
    <ul className="grid gap-2 sm:grid-cols-2">
      {alcances.map((alcance) => (
        <li key={alcance.capacidadId} className="min-w-0 rounded-lg bg-slate-50 px-3 py-2 text-sm">
          <p className="font-semibold text-slate-800">
            {alcance.nombre}{" "}
            <span className="font-normal text-slate-500">({alcance.unidad})</span>
          </p>
          <p className="mt-1 text-slate-600">Riesgo máximo: {riesgos[alcance.riesgoMaximo]}</p>
          {!alcance.activa && <p className="mt-1 font-semibold text-amber-900">Capacidad inactiva</p>}
        </li>
      ))}
    </ul>
  );
}

function FlechaAcordeon(): ReactElement {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      className="mt-1 size-5 shrink-0 text-slate-400 transition-transform group-open:rotate-180"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="m6 9 6 6 6-6" />
    </svg>
  );
}

function HistorialAcreditaciones({ perfil }: { perfil: Perfil; }): ReactElement {
  const datos = perfil.data;
  return (
    <section aria-labelledby="historial-acreditaciones" className={tarjeta}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 id="historial-acreditaciones" className="text-lg font-bold text-slate-950">
          Historial de acreditaciones
        </h3>
        {!perfil.isError && datos && (
          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
            {datos.acreditaciones.length}{" "}
            {datos.acreditaciones.length === 1 ? "acreditación" : "acreditaciones"}
          </span>
        )}
      </div>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        Todas las acreditaciones registradas, incluidas las futuras, vencidas y revocadas.
        Desplegá una para consultar sus detalles.
      </p>
      {perfil.isError ? (
        <p className={vacio}>El historial estará disponible cuando se pueda consultar el perfil de tu ONG.</p>
      ) : !datos ? (
        <p role="status" className="mt-5 text-sm text-slate-600">Consultando acreditaciones…</p>
      ) : datos.acreditaciones.length === 0 ? (
        <p className={vacio}>Tu ONG todavía no tiene acreditaciones registradas.</p>
      ) : (
        <ListadoLocal items={datos.acreditaciones} etiqueta="Desplazamiento de acreditaciones" className="mt-5">
          {(visibles) => (
            <ul
              aria-label="Listado de acreditaciones"
              className="space-y-3"
            >
              {visibles.map((credencial) => {
                const vigencia = estadosVigencia[credencial.estadoVigencia];
                return (
                  <li key={credencial.id} className="min-w-0">
                    <details name="acreditaciones-ong" className="group rounded-xl border border-slate-200">
                      <summary className="flex cursor-pointer list-none items-start justify-between gap-3 rounded-xl p-4 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700 sm:p-5">
                        <span className="min-w-0 flex-1">
                          <span className="block font-bold text-slate-950">
                            {credencial.certificacion.nombre}
                          </span>
                          <span className="mt-2 flex flex-wrap items-center gap-2">
                            <span className={`rounded-full px-3 py-1 text-xs font-bold ring-1 ring-inset ${vigencia.clase}`}>
                              {vigencia.nombre}
                            </span>
                            <span className="text-xs text-slate-500">
                              N.º <span className="font-medium text-slate-700">{credencial.numeroCredencial}</span>
                            </span>
                            <span className="text-xs text-slate-500">Revisión {credencial.certificacion.revision}</span>
                          </span>
                        </span>
                        <FlechaAcordeon />
                      </summary>
                      <div className="border-t border-slate-100 p-4 sm:p-5">
                        <dl className="grid gap-4 text-sm sm:grid-cols-3">
                          <div className="min-w-0">
                            <dt className="text-xs font-semibold text-slate-500">Emisor</dt>
                            <dd className="mt-1 text-slate-800">{credencial.emisor}</dd>
                          </div>
                          <div>
                            <dt className="text-xs font-semibold text-slate-500">Vigente desde</dt>
                            <dd className="mt-1 text-slate-800">
                              <time dateTime={credencial.vigenteDesde}>{fecha(credencial.vigenteDesde)}</time>
                            </dd>
                          </div>
                          <div>
                            <dt className="text-xs font-semibold text-slate-500">Vigente hasta</dt>
                            <dd className="mt-1 text-slate-800">
                              <time dateTime={credencial.vigenteHasta}>{fecha(credencial.vigenteHasta)}</time>
                            </dd>
                          </div>
                        </dl>
                        <div className="mt-5 border-t border-slate-100 pt-4">
                          <p className="mb-3 text-xs font-semibold text-slate-500">Alcances acreditados</p>
                          <AlcancesCertificacion alcances={credencial.certificacion.alcances} />
                        </div>
                        {credencial.motivos.map((motivo) => (
                          <p
                            key={`${motivo.codigo}-${motivo.capacidadId ?? "general"}`}
                            className="mt-3 rounded-lg bg-amber-50 p-3 text-sm leading-6 text-amber-900"
                          >
                            {motivo.mensaje}
                          </p>
                        ))}
                        {credencial.motivoRevocacion && (
                          <p className="mt-3 rounded-lg bg-rose-50 p-3 text-sm leading-6 text-rose-900">
                            Motivo de revocación: {credencial.motivoRevocacion}
                          </p>
                        )}
                      </div>
                    </details>
                  </li>
                );
              })}
            </ul>
          )}
        </ListadoLocal>
      )}
    </section>
  );
}

function CatalogoCertificaciones({
  catalogo,
}: {
  catalogo: UseQueryResult<Certificacion[]>;
}): ReactElement {
  return (
    <section aria-labelledby="catalogo-certificaciones" className={tarjeta}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 id="catalogo-certificaciones" className="text-lg font-bold text-slate-950">Catálogo nacional de certificaciones</h3>
        <span className="rounded-full bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-800">Referencia nacional</span>
      </div>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
        Consultá qué certificaciones existen y qué capacidades abarca cada una.
        Estar en este catálogo no acredita a tu ONG.
      </p>
      {catalogo.isError ? (
        <ErrorConsulta error={catalogo.error} />
      ) : !catalogo.data ? (
        <p role="status" className="mt-5 text-sm text-slate-600">Consultando catálogo…</p>
      ) : catalogo.data.length === 0 ? (
        <p className={vacio}>El catálogo no tiene certificaciones activas.</p>
      ) : (
        <ListadoLocal items={catalogo.data} etiqueta="Desplazamiento de certificaciones nacionales" className="mt-5">
          {(visibles) => (
            <ul
              aria-label="Listado de certificaciones nacionales"
              className="space-y-3"
            >
              {visibles.map((certificacion) => (
                <li key={certificacion.id} className="min-w-0">
                  <details name="catalogo-certificaciones-ong" className="group rounded-xl border border-slate-200">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-xl p-4 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700">
                      <span className="min-w-0">
                        <span className="block font-semibold text-slate-900">{certificacion.nombre}</span>
                        <span className="mt-1 block text-xs text-slate-500">Revisión {certificacion.revision} · Ver capacidades</span>
                      </span>
                      <FlechaAcordeon />
                    </summary>
                    <div className="border-t border-slate-100 p-4">
                      <AlcancesCertificacion alcances={certificacion.alcances} />
                    </div>
                  </details>
                </li>
              ))}
            </ul>
          )}
        </ListadoLocal>
      )}
    </section>
  );
}

export function CertificacionesOngPanel({
  perfil,
  catalogo,
}: {
  perfil: Perfil;
  catalogo: UseQueryResult<Certificacion[]>;
}): ReactElement {
  return (
    <section aria-labelledby="mis-certificaciones" className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 id="mis-certificaciones" className="text-xl font-bold text-slate-950">Mis certificaciones</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            Revisá por separado la situación de tu ONG, sus capacidades vigentes y
            las acreditaciones que las respaldan.
          </p>
        </div>
        <button
          type="button"
          className="action-button action-icon"
          disabled={perfil.isFetching || catalogo.isFetching}
          onClick={() => {
            void perfil.refetch();
            void catalogo.refetch();
          }}
          title="Actualizar certificaciones"
        >
          <ActionIcon name="refresh" />
          <span className="sr-only">Actualizar certificaciones</span>
        </button>
      </div>
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.5fr)]">
        <EstadoInstitucional perfil={perfil} />
        <CapacidadesHabilitadas perfil={perfil} />
      </div>
      <HistorialAcreditaciones perfil={perfil} />
      <CatalogoCertificaciones catalogo={catalogo} />
    </section>
  );
}
