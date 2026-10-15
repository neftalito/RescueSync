import { type ReactElement } from "react";
import { Link } from "react-router";

import { ActionIcon } from "../components/ActionIcon";
import { EmergenciaForm } from "../components/EmergenciaForm";

interface NuevaEmergenciaPageProps {
  csrfToken: string;
}

export function NuevaEmergenciaPage({
  csrfToken,
}: NuevaEmergenciaPageProps): ReactElement {
  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div>
            <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
              RescueSync
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-950">
              Nueva emergencia
            </h1>
          </div>
          <nav
            aria-label="Navegación de emergencias"
            className="flex flex-wrap gap-3"
          >
            <Link
              to="/mis-emergencias"
              className="action-button"
            >
              Ver mis emergencias
            </Link>
            <Link
              to="/"
              className="action-button action-icon"
              title="Volver al inicio"
            >
              <ActionIcon name="home" />
              <span className="sr-only">Volver al inicio</span>
            </Link>
          </nav>
        </div>
      </header>
      <div className="mx-auto flex max-w-6xl justify-center px-5 py-8 sm:px-6">
        <EmergenciaForm csrfToken={csrfToken} />
      </div>
    </main>
  );
}
