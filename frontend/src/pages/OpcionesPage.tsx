import type { ReactElement } from "react";
import { Link } from "react-router";

import { AppHeader } from "../components/AppHeader";
import { ChangePasswordSection } from "../components/ChangePasswordSection";
import type { Session } from "../schemas/auth";

interface OpcionesPageProps {
  session: Session;
}

export function OpcionesPage({ session }: OpcionesPageProps): ReactElement {
  return (
    <main className="flex min-h-screen flex-col bg-slate-50">
      <AppHeader session={session} />
      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center px-5 py-10 sm:px-6 sm:py-12">
        {!session.usuario.requiere_cambio_password && (
          <Link
            to="/"
            className="inline-flex min-h-11 items-center gap-2 self-start rounded-xl border border-cyan-700 bg-white px-4 py-2.5 text-sm font-semibold text-cyan-800 shadow-sm transition-colors hover:bg-cyan-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-600 active:bg-cyan-100"
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
              <path d="m12 19-7-7 7-7M5 12h14" />
            </svg>
            Volver al inicio
          </Link>
        )}
        <h1 className="mt-6 text-center text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">
          Opciones
        </h1>
        <p className="mt-3 text-center text-slate-600">
          Administrá la configuración de tu cuenta.
        </p>
        <div className="mt-8 flex justify-center">
          <ChangePasswordSection session={session} />
        </div>
      </div>
    </main>
  );
}
