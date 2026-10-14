import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { ApiError } from "../api/client";
import type {
  Certificacion,
  CertificacionesOng,
} from "../schemas/certificaciones";

const estados = {
  FUTURA: "Futura",
  VIGENTE: "Vigente",
  VENCIDA: "Vencida",
  REVOCADA: "Revocada",
};
const fecha = (valor: string): string =>
  new Date(valor).toLocaleString("es-AR");

function ErrorConsulta({ error }: { error: unknown }): ReactElement {
  return (
    <p role="alert" className="mt-3 text-red-800">
      {error instanceof ApiError
        ? error.message
        : "No pudimos consultar las certificaciones."}
    </p>
  );
}

export function CertificacionesOngPanel({
  perfil,
  catalogo,
}: {
  perfil: UseQueryResult<CertificacionesOng>;
  catalogo: UseQueryResult<Certificacion[]>;
}): ReactElement {
  return (
    <section
      aria-labelledby="mis-certificaciones"
      className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="mis-certificaciones" className="text-xl font-bold">
          Mis certificaciones
        </h2>
        <button
          type="button"
          className="rounded-xl border border-slate-300 px-4 py-2.5"
          disabled={perfil.isFetching || catalogo.isFetching}
          onClick={() => {
            void perfil.refetch();
            void catalogo.refetch();
          }}
        >
          Actualizar certificaciones
        </button>
      </div>
      <p className="mt-2 text-sm text-slate-600">
        La habilitación institucional y las credenciales determinan las
        capacidades de tu ONG. El registro y el inventario no otorgan
        certificaciones.
      </p>
      {perfil.isError ? (
        <ErrorConsulta error={perfil.error} />
      ) : !perfil.data ? (
        <p role="status" className="mt-4">
          Consultando certificaciones…
        </p>
      ) : (
        <>
          <p className="mt-4 font-semibold">
            Estado institucional: {perfil.data.estadoOng}
          </p>
          {perfil.data.motivosInstitucionales.map((motivo) => (
            <p key={motivo.codigo} className="mt-2 text-amber-900">
              {motivo.mensaje}
            </p>
          ))}
          <p className="mt-2 text-sm text-slate-600">
            Evaluado: {fecha(perfil.data.evaluadoEn)}.
          </p>
          <p className="mt-1 text-sm text-slate-600">
            Se actualiza cada minuto. Los permisos pueden cambiar y esta
            consulta no reserva recursos.
          </p>
          <h3 className="mt-5 font-bold">Capacidades habilitadas</h3>
          {perfil.data.capacidadesHabilitadas.length === 0 ? (
            <p className="mt-2">
              Tu ONG no tiene capacidades habilitadas en esta evaluación.
            </p>
          ) : (
            <ul className="mt-2 space-y-2">
              {perfil.data.capacidadesHabilitadas.map((capacidad) => (
                <li key={capacidad.capacidadId}>
                  {capacidad.nombre} ({capacidad.unidad}): riesgo máximo{" "}
                  {capacidad.riesgoMaximo}. Niveles permitidos:{" "}
                  {capacidad.nivelesRiesgoPermitidos.join(", ")}.
                </li>
              ))}
            </ul>
          )}
          <h3 className="mt-5 font-bold">Historial de acreditaciones</h3>
          {perfil.data.acreditaciones.length === 0 ? (
            <p className="mt-2">
              Tu ONG todavía no tiene acreditaciones registradas.
            </p>
          ) : (
            <ul className="mt-3 space-y-3">
              {perfil.data.acreditaciones.map((credencial) => (
                <li
                  key={credencial.id}
                  className="rounded-xl border border-slate-200 p-4"
                >
                  <p className="font-semibold">
                    {credencial.certificacion.nombre} · revisión{" "}
                    {credencial.certificacion.revision}
                  </p>
                  <p className="mt-1">
                    {estados[credencial.estadoVigencia]} ·{" "}
                    {credencial.numeroCredencial}
                  </p>
                  <p className="mt-1 text-sm">Emisor: {credencial.emisor}</p>
                  <p className="mt-1 text-sm">
                    Desde {fecha(credencial.vigenteDesde)} hasta{" "}
                    {fecha(credencial.vigenteHasta)} (fin exclusivo).
                  </p>
                  <ul className="mt-2 text-sm">
                    {credencial.certificacion.alcances.map((alcance) => (
                      <li key={alcance.capacidadId}>
                        {alcance.nombre}: riesgo máximo {alcance.riesgoMaximo}
                        {alcance.activa ? "" : " · capacidad inactiva"}.
                      </li>
                    ))}
                  </ul>
                  {credencial.motivos.map((motivo) => (
                    <p
                      key={`${motivo.codigo}-${motivo.capacidadId ?? "general"}`}
                      className="mt-1 text-sm text-amber-900"
                    >
                      {motivo.mensaje}
                    </p>
                  ))}
                  {credencial.motivoRevocacion && (
                    <p className="mt-1 text-sm">
                      Motivo de revocación: {credencial.motivoRevocacion}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <details className="mt-5">
        <summary className="cursor-pointer font-semibold">
          Catálogo nacional de certificaciones
        </summary>
        <p className="mt-2 text-sm text-slate-600">
          Catálogo de referencia. Estar en esta lista no acredita a tu ONG.
        </p>
        {catalogo.isError ? (
          <ErrorConsulta error={catalogo.error} />
        ) : !catalogo.data ? (
          <p role="status">Consultando catálogo…</p>
        ) : catalogo.data.length === 0 ? (
          <p className="mt-2">El catálogo no tiene certificaciones activas.</p>
        ) : (
          <ul className="mt-2 space-y-3">
            {catalogo.data.map((certificacion) => (
              <li key={certificacion.id}>
                <p className="font-semibold">
                  {certificacion.nombre} · revisión {certificacion.revision}
                </p>
                <ul className="text-sm">
                  {certificacion.alcances.map((alcance) => (
                    <li key={alcance.capacidadId}>
                      {alcance.nombre} ({alcance.unidad}): riesgo máximo{" "}
                      {alcance.riesgoMaximo}
                      {alcance.activa ? "" : " · inactiva"}.
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </details>
    </section>
  );
}
