import { type ReactElement } from "react";
import { Link, useParams } from "react-router";

import { OfertaForm } from "../components/OfertaForm";

interface NuevaOfertaPageProps {
  csrfToken: string;
}

export function NuevaOfertaPage({ csrfToken }: NuevaOfertaPageProps): ReactElement {
  const { ofertaId: ofertaIdParam } = useParams();
  const ofertaId =
    ofertaIdParam === undefined ? undefined : Number(ofertaIdParam);
  const editando = ofertaId !== undefined;

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div>
            <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
              RescueSync
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-950">
              {editando ? "Modificar oferta" : "Nueva oferta"}
            </h1>
          </div>
          <Link
            to="/"
            className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Volver al inicio
          </Link>
        </div>
      </header>
      <div className="mx-auto flex max-w-6xl justify-center px-5 py-8 sm:px-6">
        <OfertaForm csrfToken={csrfToken} ofertaId={ofertaId} />
      </div>
    </main>
  );
}
