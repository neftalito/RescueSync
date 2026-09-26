import { useState, type ReactElement } from "react";
import { Link } from "react-router";

import { ApiError } from "../api/client";
import { usePublicarConvocatoria } from "../hooks/usePublicarConvocatoria";
import type { Lote } from "../schemas/lote";
import { formatearFecha } from "../utils/fechas";

interface PublicarConvocatoriaProps {
  emergenciaId: number;
  csrfToken: string;
  /** Lotes de la emergencia: solo los que siguen en borrador se publican. */
  lotes: Lote[];
  /**
   * La emergencia ya está `PUBLICADA`. Se conoce desde la bandeja; al
   * terminar de publicar, la respuesta de la mutación ya lo indica por sí sola.
   */
  publicada: boolean;
}

/**
 * Publica la convocatoria de la emergencia. Es la acción explícita del
 * coordinador: guarda lotes y publica son pasos separados, y publicar es
 * irreversible para esos lotes.
 */
export function PublicarConvocatoria({
  emergenciaId,
  csrfToken,
  lotes,
  publicada,
}: PublicarConvocatoriaProps): ReactElement {
  const mutation = usePublicarConvocatoria(emergenciaId);
  // La confirmación es estado de la interfaz, no del formulario: publicar no
  // se puede deshacer y conviene exigir un segundo clic explícito.
  const [confirmando, setConfirmando] = useState(false);
  const borrador = lotes.filter((lote) => lote.estado === "BORRADOR");
  const publicadaAhora = mutation.data;

  const publicar = (): void => {
    setConfirmando(false);
    mutation.mutate(csrfToken);
  };
  const cancelar = (): void => {
    mutation.reset();
    setConfirmando(false);
  };
  const error = mutation.error instanceof ApiError
    ? mutation.error.message
    : mutation.isError
      ? "No pudimos publicar la convocatoria. Intentá nuevamente."
      : null;

  if (publicadaAhora !== undefined) {
    return (
      <section
        aria-labelledby="convocatoria-publicada"
        className="rounded-2xl border border-green-200 bg-white p-6 shadow-sm sm:p-8"
      >
        <p className="text-sm font-semibold text-cyan-800">Centro coordinador</p>
        <h2
          id="convocatoria-publicada"
          className="mt-2 text-xl font-semibold text-slate-950"
        >
          Convocatoria N.º {publicadaAhora.numero} publicada
        </h2>
        <p
          role="status"
          className="mt-3 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm leading-6 text-green-900"
        >
          Se publicaron {publicadaAhora.lotes.length}{" "}
          {publicadaAhora.lotes.length === 1 ? "lote" : "lotes"}. Las ONGs
          pueden presentar ofertas hasta el {formatearFecha(publicadaAhora.cierra_en)}.
        </p>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          Los lotes publicados ya no admiten edición. Podés revisar el estado de
          la convocatoria en el listado.
        </p>
        <div className="mt-5 flex flex-wrap gap-3">
          <Link
            to="/convocatorias"
            className="rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700"
          >
            Ver convocatorias
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section
      aria-labelledby="publicar-convocatoria"
      className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8"
    >
      <h2
        id="publicar-convocatoria"
        className="text-xl font-semibold text-slate-950"
      >
        Publicar convocatoria
      </h2>

      {publicada ? (
        <p className="mt-3 leading-7 text-slate-600">
          La convocatoria de esta emergencia ya está publicada. Los lotes que
          agregues ahora quedan en borrador para una próxima convocatoria.
        </p>
      ) : (
        <p className="mt-3 leading-7 text-slate-600">
          Al publicar, los {borrador.length}{" "}
          {borrador.length === 1 ? "lote en borrador" : "lotes en borrador"} pasarán
          a publicados y las ONGs podrán ofertar. Después no se pueden editar ni
          eliminar.
        </p>
      )}

      {error && (
        <p
          role="alert"
          className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800"
        >
          {error}
        </p>
      )}

      {confirmando ? (
        <div
          role="group"
          aria-labelledby="confirmar-publicacion"
          className="mt-5 rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-3 text-sm leading-6 text-cyan-950"
        >
          <p id="confirmar-publicacion" className="font-semibold">
            ¿Publicar la convocatoria? Los lotes en borrador quedan publicados y
            ya no se pueden editar. Esta acción no se puede deshacer.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            <button
              type="button"
              disabled={mutation.isPending}
              onClick={publicar}
              className="rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700 disabled:cursor-wait disabled:opacity-70"
            >
              {mutation.isPending ? "Publicando…" : "Sí, publicar"}
            </button>
            <button
              type="button"
              disabled={mutation.isPending}
              onClick={cancelar}
              className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700 disabled:opacity-60"
            >
              Cancelar
            </button>
          </div>
        </div>
      ) : (
        <div className="mt-5 flex flex-wrap items-center gap-4">
          <button
            type="button"
            disabled={publicada || borrador.length === 0 || mutation.isPending}
            onClick={() => setConfirmando(true)}
            className="rounded-xl bg-cyan-700 px-5 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700 disabled:cursor-not-allowed disabled:opacity-70"
            aria-busy={mutation.isPending}
          >
            {publicada
              ? "Convocatoria publicada"
              : borrador.length === 0
                ? "Sin lotes en borrador"
                : "Publicar convocatoria"}
          </button>
          {borrador.length === 0 && !publicada && (
            <p className="text-sm leading-6 text-slate-600">
              Guardá al menos un lote en borrador para poder publicar.
            </p>
          )}
        </div>
      )}
    </section>
  );
}
