import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactElement,
} from "react";
import { Link } from "react-router";

import {
  marcarNotificacionLeida,
  marcarTodasLasNotificacionesLeidas,
} from "../api/notificaciones";
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
  const contenedorRef = useRef<HTMLDivElement>(null);
  const botonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);

  useLayoutEffect(() => {
    if (!abierto) return;

    const posicionarPanel = (): void => {
      const boton = botonRef.current;
      const panel = panelRef.current;
      if (!boton || !panel) return;

      // Conserva el anclaje al botón sin salir de la ventana si el header se envuelve.
      const rect = boton.getBoundingClientRect();
      const left = Math.max(
        16,
        Math.min(
          rect.right - panel.offsetWidth,
          window.innerWidth - panel.offsetWidth - 16,
        ),
      );
      const top = Math.max(16, Math.min(rect.bottom + 8, window.innerHeight - 160));
      panel.style.setProperty("--notification-left", `${left}px`);
      panel.style.setProperty("--notification-top", `${top}px`);
      panel.style.setProperty(
        "--notification-max-height",
        `${window.innerHeight - top - 16}px`,
      );
    };

    posicionarPanel();
    window.addEventListener("resize", posicionarPanel);
    window.addEventListener("scroll", posicionarPanel, true);
    return () => {
      window.removeEventListener("resize", posicionarPanel);
      window.removeEventListener("scroll", posicionarPanel, true);
    };
  }, [abierto]);

  useEffect(() => {
    if (!abierto) return;

    const cerrarFuera = (event: PointerEvent): void => {
      if (
        event.target instanceof Node &&
        !contenedorRef.current?.contains(event.target)
      ) {
        setAbierto(false);
      }
    };
    const cerrarConEscape = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        setAbierto(false);
        botonRef.current?.focus();
      }
    };

    document.addEventListener("pointerdown", cerrarFuera, true);
    document.addEventListener("keydown", cerrarConEscape);
    return () => {
      document.removeEventListener("pointerdown", cerrarFuera, true);
      document.removeEventListener("keydown", cerrarConEscape);
    };
  }, [abierto]);

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
  const marcarTodasLeidas = useMutation({
    mutationFn: () => marcarTodasLasNotificacionesLeidas(csrfToken),
    onSuccess: (resultado) => {
      queryClient.setQueryData<Notificacion[]>(
        notificacionesQueryKey,
        (anteriores = []) =>
          anteriores.map((notificacion) =>
            notificacion.leida_en === null
              ? { ...notificacion, leida_en: resultado.leida_en }
              : notificacion,
          ),
      );
    },
  });
  const noLeidas = query.data?.filter((item) => item.leida_en === null).length ?? 0;
  const error = marcarLeida.error ?? marcarTodasLeidas.error;
  const errorMutacion =
    error instanceof ApiError
      ? error.message
      : error !== null
        ? "No pudimos actualizar la notificación."
        : null;

  const leer = (notificacion: Notificacion): void => {
    if (notificacion.leida_en === null) marcarLeida.mutate(notificacion.id);
  };

  return (
    <div ref={contenedorRef} className="relative">
      <button
        ref={botonRef}
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
          ref={panelRef}
          id="panel-notificaciones"
          aria-label="Notificaciones"
          className="fixed inset-x-4 bottom-4 z-20 flex max-h-[calc(100dvh-2rem)] flex-col rounded-2xl border border-slate-200 bg-white p-4 shadow-xl sm:inset-x-auto sm:top-[var(--notification-top)] sm:bottom-auto sm:left-[var(--notification-left)] sm:max-h-[min(32rem,var(--notification-max-height))] sm:w-[min(24rem,calc(100vw-2rem))]"
        >
          <div className="flex shrink-0 flex-wrap items-center gap-3">
            <h2 className="font-semibold text-slate-950">Novedades</h2>
            <div className="ml-auto flex items-center gap-2">
              <span className="text-xs text-slate-500">{noLeidas} sin leer</span>
              <button
                type="button"
                aria-label="Marcar todas como vistas"
                title="Marcar todas como vistas"
                disabled={noLeidas === 0 || marcarTodasLeidas.isPending}
                onClick={() => marcarTodasLeidas.mutate()}
                className="inline-flex size-8 items-center justify-center rounded-lg text-cyan-800 hover:bg-cyan-50 disabled:cursor-not-allowed disabled:text-slate-300 disabled:hover:bg-transparent"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="size-5"
                >
                  <path d="m1 12 5 5L16 7" />
                  <path d="m8 12 5 5L23 7" />
                </svg>
              </button>
            </div>
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
            <ul className="mt-3 min-h-0 space-y-2 overflow-y-auto overscroll-contain">
              {query.data.map((notificacion) => (
                <li
                  key={notificacion.id}
                  className={`rounded-xl border p-3 [overflow-wrap:anywhere] ${
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
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
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
            <p role="alert" className="mt-3 shrink-0 text-sm text-red-800">
              {errorMutacion}
            </p>
          )}
        </section>
      )}
    </div>
  );
}
