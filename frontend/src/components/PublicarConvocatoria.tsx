import { useState, type ReactElement } from "react";
import { Link } from "react-router";
import type { UseMutationResult } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { usePublicarConvocatoria } from "../hooks/usePublicarConvocatoria";
import type { Convocatoria } from "../schemas/convocatoria";
import { formatearFecha } from "../utils/fechas";

interface PublicarConvocatoriaProps {
  emergenciaId: number;
  csrfToken: string;
  /**
   * Lotes de la emergencia que siguen en borrador. Solo hace falta el conteo,
   * no el detalle: el backend vuelve a validar cuáles se publican, y la bandeja
   * no carga los lotes de cada fila.
   */
  cantidadBorrador: number;
  /**
   * La emergencia ya está `PUBLICADA` y no admite otra convocatoria. La bandeja
   * nunca trae emergencias en ese estado; el detalle de lotes sí, y entonces la
   * acción no debe prometer una publicación imposible.
   */
  publicada: boolean;
  /**
   * Notifica el resultado en vez de mostrarlo. La bandeja lo necesita: al
   * publicar, la emergencia sale del listado y la fila se desmonta, así que el
   * panel no alcanza a pintar su propio estado de éxito.
   */
  onPublicado?: (convocatoria: Convocatoria) => void;
}

type Mutacion = UseMutationResult<Convocatoria, ApiError | Error, string>;

/**
 * Publica la convocatoria de la emergencia. Es la acción explícita del
 * coordinador: guardar lotes y publicar son pasos separados, y publicar es
 * irreversible para esos lotes.
 */
export function PublicarConvocatoria({
  emergenciaId,
  csrfToken,
  cantidadBorrador,
  publicada,
  onPublicado,
}: PublicarConvocatoriaProps): ReactElement {
  const mutation = usePublicarConvocatoria(emergenciaId);
  // La confirmación es estado de la interfaz, no del formulario: publicar no se
  // puede deshacer y conviene exigir un segundo clic explícito.
  const [confirmando, setConfirmando] = useState(false);
  const publicadaAhora = mutation.data;
  // Se renderiza una vez por emergencia en la bandeja, así que los id no pueden
  // ser fijos o quedarían duplicados.
  const tituloId = `publicar-convocatoria-${emergenciaId}`;
  const confirmacionId = `confirmar-publicacion-${emergenciaId}`;

  const publicar = (): void => {
    setConfirmando(false);
    mutation.mutate(csrfToken, {
      onSuccess: (convocatoria) => onPublicado?.(convocatoria),
    });
  };
  const cancelar = (): void => {
    mutation.reset();
    setConfirmando(false);
  };
  const error =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.isError
        ? "No pudimos publicar la convocatoria. Intentá nuevamente."
        : null;

  if (onPublicado !== undefined) {
    return (
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
        <AccionPublicar
          cantidadBorrador={cantidadBorrador}
          mutation={mutation}
          confirmando={confirmando}
          confirmacionId={confirmacionId}
          error={error}
          onConfirmar={publicar}
          onCancelar={cancelar}
          onPedirConfirmacion={() => setConfirmando(true)}
        />
      </div>
    );
  }

  if (publicadaAhora !== undefined) {
    return (
      <section
        aria-labelledby={tituloId}
        className="rounded-2xl border border-green-200 bg-white p-6 shadow-sm sm:p-8"
      >
        <p className="text-sm font-semibold text-cyan-800">Centro coordinador</p>
        <h2 id={tituloId} className="mt-2 text-xl font-semibold text-slate-950">
          Convocatoria N.º {publicadaAhora.numero} publicada
        </h2>
        <p
          role="status"
          className="mt-3 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm leading-6 text-green-900"
        >
          Se publicaron {publicadaAhora.lotes.length}{" "}
          {publicadaAhora.lotes.length === 1 ? "lote" : "lotes"}. Las ONGs pueden
          presentar ofertas hasta el {formatearFecha(publicadaAhora.cierra_en)}.
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
      aria-labelledby={tituloId}
      className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8"
    >
      <h2 id={tituloId} className="text-xl font-semibold text-slate-950">
        Publicar convocatoria
      </h2>

      {publicada ? (
        <p className="mt-3 leading-7 text-slate-600">
          La convocatoria de esta emergencia ya se publicó y no admite otra. Los
          lotes que agregues quedan en borrador.
        </p>
      ) : (
        <p className="mt-3 leading-7 text-slate-600">
          <ResumenBorrador cantidadBorrador={cantidadBorrador} />
        </p>
      )}

      <AccionPublicar
        cantidadBorrador={cantidadBorrador}
        mutation={mutation}
        confirmando={confirmando}
        confirmacionId={confirmacionId}
        error={error}
        onConfirmar={publicar}
        onCancelar={cancelar}
        onPedirConfirmacion={() => setConfirmando(true)}
        published={publicada}
      />
    </section>
  );
}

function ResumenBorrador({ cantidadBorrador }: { cantidadBorrador: number }): ReactElement {
  return (
    <>
      Al publicar, los {cantidadBorrador}{" "}
      {cantidadBorrador === 1 ? "lote en borrador" : "lotes en borrador"} pasarán a
      publicados y las ONGs podrán ofertar. Después no se pueden editar ni eliminar.
    </>
  );
}

interface AccionPublicarProps {
  cantidadBorrador: number;
  mutation: Mutacion;
  confirmando: boolean;
  confirmacionId: string;
  error: string | null;
  onConfirmar: () => void;
  onCancelar: () => void;
  onPedirConfirmacion: () => void;
  /** Etiqueta del botón cuando la emergencia ya no admite publicación. */
  published?: boolean;
}

/** Confirmación en dos pasos y botón de publicación, compartidos por ambas pantallas. */
function AccionPublicar({
  cantidadBorrador,
  mutation,
  confirmando,
  confirmacionId,
  error,
  onConfirmar,
  onCancelar,
  onPedirConfirmacion,
  published = false,
}: AccionPublicarProps): ReactElement {
  const sinBorrador = !published && cantidadBorrador === 0;

  return (
    <>
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
          aria-labelledby={confirmacionId}
          className="mt-5 rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-3 text-sm leading-6 text-cyan-950"
        >
          <p id={confirmacionId} className="font-semibold">
            ¿Publicar la convocatoria? Los lotes en borrador quedan publicados y
            ya no se pueden editar. Esta acción no se puede deshacer.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            <button
              type="button"
              disabled={mutation.isPending}
              onClick={onConfirmar}
              className="rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700 disabled:cursor-wait disabled:opacity-70"
            >
              {mutation.isPending ? "Publicando…" : "Sí, publicar"}
            </button>
            <button
              type="button"
              disabled={mutation.isPending}
              onClick={onCancelar}
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
            disabled={published || sinBorrador || mutation.isPending}
            onClick={onPedirConfirmacion}
            className="rounded-xl bg-cyan-700 px-5 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700 disabled:cursor-not-allowed disabled:opacity-70"
            aria-busy={mutation.isPending}
          >
            {published
              ? "Convocatoria publicada"
              : sinBorrador
                ? "Sin lotes en borrador"
                : "Publicar convocatoria"}
          </button>
          {sinBorrador && (
            <p className="text-sm leading-6 text-slate-600">
              Guardá al menos un lote en borrador para poder publicar.
            </p>
          )}
        </div>
      )}
    </>
  );
}
