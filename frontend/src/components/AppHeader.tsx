import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { Link, useNavigate } from "react-router";

import { ActionIcon } from "./ActionIcon";
import { logout } from "../api/auth";
import { ApiError } from "../api/client";
import { roleLabels, type Session } from "../schemas/auth";
import { NotificationCenter } from "./NotificationCenter";

interface AppHeaderProps {
  session: Session;
}

export function AppHeader({ session }: AppHeaderProps): ReactElement {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => logout(session.csrf_token),
    onSuccess: () => {
      // Evita mostrar datos de esta cuenta a la siguiente persona que ingrese.
      queryClient.clear();
      navigate("/login", { replace: true });
    },
  });
  const logoutError =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.isError
        ? "No pudimos cerrar la sesión. Intentá nuevamente."
        : null;

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-6 gap-y-4 px-5 py-4 sm:px-6 lg:grid-cols-[minmax(0,1fr)_auto_auto] lg:items-center">
        <div className="min-w-0">
          <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
            RescueSync
          </p>
          <p className="mt-1 text-sm text-slate-500">
            Coordinación regional ante emergencias
          </p>
        </div>
        {!session.usuario.requiere_cambio_password && (
          <div className="col-span-2 col-start-1 row-start-2 flex min-w-0 flex-wrap items-center gap-3 lg:col-span-1 lg:col-start-2 lg:row-start-1">
            <div className="hidden min-w-0 text-right sm:block">
              <p className="max-w-64 truncate text-sm font-semibold text-slate-900">
                {session.usuario.email}
              </p>
              <p className="text-xs text-slate-500">
                {roleLabels[session.usuario.rol]}
              </p>
            </div>
            {session.usuario.rol === "ADMINISTRADOR" && (
              <Link
                to="/usuarios"
                className="action-button action-primary action-icon"
                title="Usuarios"
              >
                <ActionIcon name="users" />
                <span className="sr-only">Usuarios</span>
              </Link>
            )}
            <NotificationCenter csrfToken={session.csrf_token} />
            <Link
              to="/opciones"
              aria-label="Opciones"
              title="Opciones"
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-xl border border-slate-300 bg-white text-slate-600 outline-2 outline-offset-2 outline-transparent transition-colors hover:border-gray-500 hover:bg-gray-50 hover:text-gray-700 hover:outline-gray-500 focus-visible:outline-gray-600 active:border-gray-700 active:bg-gray-100 active:text-gray-900 active:outline-gray-700"
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
              >
                <path
                  d="m9.7 4.3.5-2.3h3.6l.5 2.3 1.8 1 2.3-.7 1.8 3.1-1.8 1.6v2.1l1.8 1.6-1.8 3.1-2.3-.7-1.8 1-.5 2.3h-3.6l-.5-2.3-1.8-1-2.3.7-1.8-3.1 1.8-1.6V9.3L4.3 7.7l1.8-3.1 2.3.7z"
                  transform="translate(0 1)"
                />
                <circle cx="12" cy="11.5" r="3" />
              </svg>
            </Link>
          </div>
        )}
        <div className="col-start-2 row-start-1 border-l border-slate-200 pl-4 lg:col-start-3 lg:pl-6">
          <button
            type="button"
            aria-label={mutation.isPending ? "Saliendo…" : "Cerrar sesión"}
            aria-busy={mutation.isPending}
            title="Cerrar sesión"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
            className="inline-flex size-11 shrink-0 items-center justify-center rounded-xl border border-slate-300 bg-white text-slate-600 outline-2 outline-offset-2 outline-transparent transition-colors hover:border-red-500 hover:bg-red-50 hover:text-red-700 hover:outline-red-500 focus-visible:outline-red-600 active:border-red-700 active:bg-red-100 active:text-red-900 active:outline-red-700 disabled:cursor-wait disabled:opacity-60"
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
            >
              <path d="M9 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h4" />
              <path d="m16 7 5 5-5 5M21 12H9" />
            </svg>
          </button>
        </div>
      </div>
      {logoutError && (
        <p
          role="alert"
          className="mx-5 mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 sm:mx-6"
        >
          {logoutError}
        </p>
      )}
    </header>
  );
}
