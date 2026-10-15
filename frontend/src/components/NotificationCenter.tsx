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
import { ListadoRemoto } from "./ListadoProgresivo";
import { ActionIcon } from "./ActionIcon";
import { ApiError } from "../api/client";
import {
  notificacionesQueryKey,
  useNotificaciones,
  useNotificacionesPaginadas,
} from "../hooks/useNotificaciones";
import { actualizarPaginas } from "../utils/actualizarPaginas";
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
      const top = Math.max(
        16,
        Math.min(rect.bottom + 8, window.innerHeight - 160),
      );
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
  const historial = useNotificacionesPaginadas(abierto);
  const queryClient = useQueryClient();
  const marcarLeida = useMutation({
    mutationFn: (notificacionId: number) =>
      marcarNotificacionLeida(notificacionId, csrfToken),
    onSuccess: (actualizada) => {
      actualizarPaginas<Notificacion>(queryClient, notificacionesQueryKey,
        (notificacion) => notificacion.id === actualizada.id ? actualizada : notificacion);
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
      actualizarPaginas<Notificacion>(queryClient, notificacionesQueryKey,
        (notificacion) => notificacion.leida_en === null ? { ...notificacion, leida_en: resultado.leida_en } : notificacion);
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
  const noLeidas =
    query.data?.filter((item) => item.leida_en === null).length ?? 0;
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
        aria-label="Notificaciones"
        aria-describedby="estado-notificaciones"
        title={
          noLeidas > 0
            ? `Notificaciones: ${noLeidas} sin leer`
            : "Notificaciones"
        }
        aria-expanded={abierto}
        aria-controls="panel-notificaciones"
        onClick={() => setAbierto((valor) => !valor)}
        className={`inline-flex size-11 shrink-0 items-center justify-center rounded-xl border border-slate-300 bg-white outline-2 outline-offset-2 outline-transparent transition-colors hover:border-yellow-500 hover:bg-yellow-50 hover:text-yellow-700 hover:outline-yellow-500 focus-visible:outline-yellow-600 active:border-yellow-700 active:bg-yellow-100 active:text-yellow-900 active:outline-yellow-700 ${noLeidas > 0 ? "text-yellow-600" : "text-slate-600"}`}
      >
        <svg
          aria-hidden="true"
          focusable="false"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="size-5"
          data-estado={noLeidas > 0 ? "sonando" : "quieta"}
        >
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
          <path d="M10 21h4" />
          {noLeidas > 0 && (
            <path d="M2 8a10 10 0 0 1 2-5m18 5a10 10 0 0 0-2-5" />
          )}
        </svg>
      </button>
      <span id="estado-notificaciones" className="sr-only" aria-live="polite">
        {noLeidas > 0
          ? `${noLeidas} ${noLeidas === 1 ? "notificación sin leer" : "notificaciones sin leer"}`
          : "No hay notificaciones sin leer"}
      </span>

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
              <span className="text-xs text-slate-500">
                {noLeidas} sin leer
              </span>
              <button
                type="button"
                aria-label="Marcar todas como vistas"
                title="Marcar todas como vistas"
                disabled={noLeidas === 0 || marcarTodasLeidas.isPending}
                onClick={() => marcarTodasLeidas.mutate()}
                className="action-button action-primary action-icon action-borderless"
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

          {historial.isPending ? (
            <p role="status" className="py-6 text-sm text-slate-500">
              Cargando notificaciones…
            </p>
          ) : historial.data === undefined ? (
            <div role="alert" className="py-5 text-sm text-red-800">
              <p>No pudimos cargar las notificaciones.</p>
              <button
                type="button"
                onClick={() => void historial.refetch()}
                className="action-button action-icon mt-3"
                title="Reintentar"
              >
                <ActionIcon name="refresh" />
                <span className="sr-only">Reintentar</span>
              </button>
            </div>
          ) : historial.data.length === 0 ? (
            <p role="status" className="py-6 text-sm text-slate-500">
              No hay novedades todavía.
            </p>
          ) : (
            <ListadoRemoto query={historial} etiqueta="Historial de notificaciones" className="mt-3">
              <ul className="space-y-2">
                {historial.data.map((notificacion) => (
                  <li
                    key={notificacion.id}
                    className={`rounded-xl border p-3 [overflow-wrap:anywhere] ${notificacion.leida_en === null
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
                          className="action-button action-primary action-icon"
                          title="Ver detalle"
                        >
                          <ActionIcon name="eye" />
                          <span className="sr-only">Ver detalle</span>
                        </Link>
                      ) : notificacion.leida_en === null ? (
                        <button
                          type="button"
                          onClick={() => leer(notificacion)}
                          className="action-button action-primary action-icon action-borderless"
                          title="Marcar como leída"
                        >
                          <ActionIcon name="check" />
                          <span className="sr-only">Marcar como leída</span>
                        </button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            </ListadoRemoto>
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
