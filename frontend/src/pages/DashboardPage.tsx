import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ReactElement } from "react";
import { useNavigate } from "react-router";

import { logout } from "../api/auth";
import { ApiError } from "../api/client";
import { EmergenciaForm } from "../components/EmergenciaForm";
import { sessionQueryKey } from "../hooks/useSession";
import { roleLabels, type Role, type Session } from "../schemas/auth";

interface DashboardPageProps {
  session: Session;
}

interface Stage {
  role: Role;
  actor: string;
  title: string;
  description: string;
}

const stages: Stage[] = [
  {
    role: "COORDINADOR_REGIONAL",
    actor: "Centro coordinador",
    title: "Generar y publicar lotes",
    description: "Necesidades cuantificadas antes de abrir la convocatoria.",
  },
  {
    role: "REPRESENTANTE_ONG",
    actor: "ONG",
    title: "Presentar oferta",
    description: "Recursos y personal para uno o más lotes publicados.",
  },
];

export function DashboardPage({ session }: DashboardPageProps): ReactElement {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => logout(session.csrf_token),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: sessionQueryKey });
      navigate("/login", { replace: true });
    },
  });
  const logoutError =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.isError
        ? "No pudimos cerrar la sesión. Intentá nuevamente."
        : null;
  const visibleStages = stages.filter(
    (stage) => stage.role === session.usuario.rol,
  );
  const esMunicipio = session.usuario.rol === "OPERADOR_MUNICIPAL";

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div>
            <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
              RescueSync
            </p>
            <p className="mt-1 text-sm text-slate-500">
              Coordinación regional ante emergencias
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold text-slate-900">
                {session.usuario.email}
              </p>
              <p className="text-xs text-slate-500">
                {roleLabels[session.usuario.rol]}
              </p>
            </div>
            <button
              type="button"
              disabled={mutation.isPending}
              onClick={() => mutation.mutate()}
              className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700 disabled:cursor-wait disabled:opacity-60"
            >
              {mutation.isPending ? "Saliendo…" : "Cerrar sesión"}
            </button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-6xl px-5 py-12 sm:px-6 sm:py-16">
        {logoutError && (
          <p
            role="alert"
            className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          >
            {logoutError}
          </p>
        )}

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
          <div>
            <span className="rounded-full bg-cyan-100 px-3 py-1 text-sm font-semibold text-cyan-900">
              Sesión activa
            </span>
            <h1 className="mt-5 text-3xl font-bold tracking-tight text-slate-950 sm:text-5xl">
              Bienvenido a RescueSync
            </h1>
            <p className="mt-4 max-w-2xl text-lg leading-8 text-slate-600">
              Tu acceso está listo. Las funciones operativas aparecerán según tu
              rol a medida que se integren las historias de la Entrega 2.
            </p>
          </div>

          <aside className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <p className="text-xs font-bold tracking-[0.14em] text-slate-500 uppercase">
              Tu perfil
            </p>
            <dl className="mt-4 space-y-4 text-sm">
              <div>
                <dt className="text-slate-500">Rol</dt>
                <dd className="mt-1 font-semibold text-slate-950">
                  {roleLabels[session.usuario.rol]}
                </dd>
              </div>
              <div>
                <dt className="text-slate-500">Organización</dt>
                <dd className="mt-1 font-semibold text-slate-950">
                  {session.usuario.organizacion?.nombre ?? "Sin organización"}
                </dd>
              </div>
            </dl>
          </aside>
        </div>

        <section className="mt-12" aria-labelledby="acciones-rol">
          <h2
            id="acciones-rol"
            className="text-xl font-semibold text-slate-950"
          >
            Acciones disponibles para tu rol
          </h2>

          {esMunicipio ? (
            <div className="mt-5">
              <EmergenciaForm csrfToken={session.csrf_token} />
            </div>
          ) : visibleStages.length === 0 ? (
            <article className="mt-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-xl font-semibold text-slate-950">
                Perfil preparado para auditoría
              </h3>
              <p className="mt-3 max-w-2xl leading-7 text-slate-600">
                Este perfil no tiene operaciones funcionales en la Entrega 2.
                Las consultas e indicadores se incorporarán en etapas posteriores.
              </p>
            </article>
          ) : (
            <div className="mt-5 grid gap-5 md:grid-cols-3">
              {visibleStages.map((stage, index) => (
                <article
                  key={stage.actor}
                  className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-cyan-800">
                      {stage.actor}
                    </span>
                    <span className="grid size-8 place-items-center rounded-full bg-slate-100 text-sm font-semibold text-slate-600">
                      {index + 1}
                    </span>
                  </div>
                  <h3 className="mt-8 text-xl font-semibold text-slate-950">
                    {stage.title}
                  </h3>
                  <p className="mt-3 leading-7 text-slate-600">
                    {stage.description}
                  </p>
                  <button
                    type="button"
                    disabled
                    className="mt-8 w-full cursor-not-allowed rounded-xl bg-slate-100 px-4 py-2.5 text-sm font-semibold text-slate-400"
                  >
                    Próximamente
                  </button>
                </article>
              ))}
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
