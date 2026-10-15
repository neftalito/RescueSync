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
    <main className="min-h-screen bg-slate-50">
      <AppHeader session={session} />
      <div className="mx-auto max-w-6xl px-5 py-10 sm:px-6 sm:py-12">
        {!session.usuario.requiere_cambio_password && (
          <Link
            to="/"
            className="text-sm font-semibold text-cyan-800 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-600"
          >
            Volver al inicio
          </Link>
        )}
        <h1 className="mt-4 text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">
          Opciones
        </h1>
        <p className="mt-3 text-slate-600">
          Administrá la configuración de tu cuenta.
        </p>
        <div className="mt-8">
          <ChangePasswordSection session={session} />
        </div>
      </div>
    </main>
  );
}
