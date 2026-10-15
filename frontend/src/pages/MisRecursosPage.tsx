import type { ReactElement } from "react";
import { Link } from "react-router";
import type { Session } from "../schemas/auth";

export function MisRecursosPage({ session }: { session: Session }): ReactElement {
  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div>
            <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
              RescueSync
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-950">Mis recursos</h1>
          </div>
          <Link
            to="/"
            className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Volver al inicio
          </Link>
        </div>
      </header>

      <div className="mx-auto max-w-6xl space-y-6 px-5 py-8 sm:px-6">
        <div>
          <p className="text-sm font-semibold text-cyan-800">
            {session.usuario.organizacion?.nombre}
          </p>
          <p className="mt-2 text-slate-600">
            Elegí qué información de tu ONG querés consultar o gestionar.
          </p>
        </div>
        <div className="grid gap-5 md:grid-cols-2">
          <article className="flex flex-col rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-xl font-semibold text-slate-950">Mis certificaciones</h2>
            <p className="mt-3 flex-1 leading-7 text-slate-600">
              Consultá tus acreditaciones, su vigencia y las capacidades
              habilitadas de tu ONG.
            </p>
            <Link
              to="/mis-recursos/certificaciones"
              className="mt-6 inline-flex self-start rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800"
            >
              Ver mis certificaciones
            </Link>
          </article>
          <article className="flex flex-col rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-xl font-semibold text-slate-950">Inventario de mi ONG</h2>
            <p className="mt-3 flex-1 leading-7 text-slate-600">
              Registrá recursos y consultá o actualizá las cantidades totales,
              comprometidas y disponibles de tu inventario.
            </p>
            <Link
              to="/mis-recursos/inventario"
              className="mt-6 inline-flex self-start rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800"
            >
              Gestionar inventario
            </Link>
          </article>
        </div>
      </div>
    </main>
  );
}
