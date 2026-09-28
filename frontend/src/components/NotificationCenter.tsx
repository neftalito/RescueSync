import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactElement } from "react";
import { Link } from "react-router";

import { marcarNotificacionLeida } from "../api/notificaciones";
import { ApiError } from "../api/client";
import {
  notificacionesQueryKey,
  useNotificaciones,
} from "../hooks/useNotificaciones";
import type { Notificacion } from "../schemas/notificacion";

interface NotificationCenterProps {
  csrfToken: string;
}

function formatearFecha(fecha: string): string {
  return new Date(fecha).toLocaleString("es-AR", {
    dateStyle: "short",
    timeStyle: "short",
  });
}

export function NotificationCenter({
  csrfToken,
}: NotificationCenterProps): ReactElement {
  const [abierto, setAbierto] = useState(false);
  const query = useNotificaciones();
  const queryClient = useQueryClient();
  const marcarLeida = useMutation({
    mutationFn: (notificacionId: number) =>
      marcarNotificacionLeida(notificacionId, csrfToken),
    onSuccess: (actualizada) => {
      queryClient.setQueryData<Notificacion[]>(
        notificacionesQueryKey,
        (anteriores = []) =>
          anteriores.map((notificacion) =>
            notificacion.id === actualizada.id ? actualizada : notificacion,
          ),
      );
    },
  });
  const noLeidas = query.data?.filter((item) => item.leida_en === null).length ?? 0;
  const errorMutacion =
    marcarLeida.error instanceof ApiError
      ? marcarLeida.error.message
      : marcarLeida.isError
        ? "No pudimos actualizar la notificación."
        : null;

  const leer = (notificacion: Notificacion): void => {
    if (notificacion.leida_en === null) marcarLeida.mutate(notificacion.id);
  };

  return (
    <div className="relative">
      <button
        type="button"
        aria-expanded={abierto}
        aria-controls="panel-notificaciones"
        onClick={() => setAbierto((valor) => !valor)}
        className="relative rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
      >
        Notificaciones
        {noLeidas > 0 && (
          <span className="ml-2 inline-flex min-w-5 justify-center rounded-full bg-red-600 px-1.5 py-0.5 text-xs text-white">
            {noLeidas > 99 ? "99+" : noLeidas}
          </span>
        )}
      </button>

      {abierto && (
        <section
          id="panel-notificaciones"
          aria-label="Notificaciones"
          className="absolute right-0 z-20 mt-2 w-[min(24rem,calc(100vw-2rem))] rounded-2xl border border-slate-200 bg-white p-4 shadow-xl"
        >
          <div className="flex items-center justify-between gap-3">
            <h2 className="font-semibold text-slate-950">Novedades</h2>
            <span className="text-xs text-slate-500">{noLeidas} sin leer</span>
          </div>

          {query.isPending ? (
            <p role="status" className="py-6 text-sm text-slate-500">
              Cargando notificaciones…
            </p>
          ) : query.isError ? (
            <div role="alert" className="py-5 text-sm text-red-800">
              <p>No pudimos cargar las notificaciones.</p>
              <button
                type="button"
                onClick={() => void query.refetch()}
                className="mt-3 font-semibold underline"
              >
                Reintentar
              </button>
            </div>
          ) : query.data.length === 0 ? (
            <p role="status" className="py-6 text-sm text-slate-500">
              No hay novedades todavía.
            </p>
          ) : (
            <ul className="mt-3 max-h-96 space-y-2 overflow-y-auto">
              {query.data.map((notificacion) => (
                <li
                  key={notificacion.id}
                  className={`rounded-xl border p-3 ${
                    notificacion.leida_en === null
                      ? "border-cyan-200 bg-cyan-50"
                      : "border-slate-200 bg-white"
                  }`}
                >
                  <p className="text-sm font-semibold text-slate-950">
                    {notificacion.titulo}
                  </p>
                  <p className="mt-1 text-sm leading-5 text-slate-600">
                    {notificacion.mensaje}
                  </p>
                  <div className="mt-2 flex items-center justify-between gap-3">
                    <time className="text-xs text-slate-500">
                      {formatearFecha(notificacion.creada_en)}
                    </time>
                    {notificacion.ruta ? (
                      <Link
                        to={notificacion.ruta}
                        onClick={() => leer(notificacion)}
                        className="text-xs font-semibold text-cyan-800 underline"
                      >
                        Ver detalle
                      </Link>
                    ) : notificacion.leida_en === null ? (
                      <button
                        type="button"
                        onClick={() => leer(notificacion)}
                        className="text-xs font-semibold text-cyan-800 underline"
                      >
                        Marcar como leída
                      </button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
          {errorMutacion && (
            <p role="alert" className="mt-3 text-sm text-red-800">
              {errorMutacion}
            </p>
          )}
        </section>
      )}
    </div>
  );
}
