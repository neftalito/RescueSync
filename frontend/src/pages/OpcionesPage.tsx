import type { ReactElement } from "react";
import { Link } from "react-router";

import { ActionIcon } from "../components/ActionIcon";
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
            className="action-button action-icon self-start"
            title="Volver al inicio"
          >
            <ActionIcon name="home" />
            <span className="sr-only">Volver al inicio</span>
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
