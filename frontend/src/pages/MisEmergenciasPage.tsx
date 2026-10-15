import { type ReactElement } from "react";
import { Link } from "react-router";

import { BandejaEmergencias } from "../components/BandejaEmergencias";

interface MisEmergenciasPageProps {
  csrfToken: string;
}

export function MisEmergenciasPage({
  csrfToken,
}: MisEmergenciasPageProps): ReactElement {
  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div>
            <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
              RescueSync
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-950">
              Emergencias de mi municipio
            </h1>
          </div>
          <nav
            aria-label="Navegación de emergencias"
            className="flex flex-wrap gap-3"
          >
            <Link
              to="/emergencias/nueva"
              className="rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800"
            >
              Registrar emergencia
            </Link>
            <Link
              to="/"
              className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              Volver al inicio
            </Link>
          </nav>
        </div>
      </header>
      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-6">
        <BandejaEmergencias rol="OPERADOR_MUNICIPAL" csrfToken={csrfToken} />
      </div>
    </main>
  );
}
