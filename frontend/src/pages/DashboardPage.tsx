import { useMutation, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, type ReactElement } from "react";
import { Link, useNavigate } from "react-router";

import { logout } from "../api/auth";
import { ApiError } from "../api/client";
import { BandejaEmergencias } from "../components/BandejaEmergencias";
import { NotificationCenter } from "../components/NotificationCenter";
import { roleLabels, type Role, type Session } from "../schemas/auth";

const DashboardAuditor = lazy(() =>
  import("../components/DashboardAuditor").then((modulo) => ({
    default: modulo.DashboardAuditor,
  })),
);

const responsabilidadesPorRol: Record<Role, string> = {
  OPERADOR_MUNICIPAL:
    "Registrás las emergencias de tu municipio y hacés seguimiento de su estado.",
  COORDINADOR_REGIONAL:
    "Organizás las necesidades de las emergencias de tu región en lotes y publicás convocatorias para recibir ofertas de las ONG.",
  REPRESENTANTE_ONG:
    "Gestionás los recursos de tu ONG, consultás convocatorias y presentás y actualizás ofertas de ayuda.",
  AUDITOR_DIRECTIVO:
    "Tu responsabilidad es supervisar la gestión de emergencias y evaluar sus resultados.",
  ADMINISTRADOR:
    "Administrás usuarios, roles y organizaciones, y mantenés el catálogo nacional de capacidades.",
};

interface DashboardPageProps {
  session: Session;
}

export function DashboardPage({ session }: DashboardPageProps): ReactElement {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => logout(session.csrf_token),
    onSuccess: () => {
      // Limpia todo el caché (no solo la sesión): sin esto, una bandeja
      // consultada por este usuario podría seguir en caché y mostrarse
      // brevemente a la siguiente persona que inicie sesión en la misma
      // pestaña, antes de que ese query vuelva a pedirse.
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
  const esMunicipio = session.usuario.rol === "OPERADOR_MUNICIPAL";
  const esCoordinador = session.usuario.rol === "COORDINADOR_REGIONAL";
  const esOng = session.usuario.rol === "REPRESENTANTE_ONG";
  const esAuditor = session.usuario.rol === "AUDITOR_DIRECTIVO";

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
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold text-slate-900">
                {session.usuario.email}
              </p>
              <p className="text-xs text-slate-500">
                {roleLabels[session.usuario.rol]}
              </p>
            </div>
            {session.usuario.rol === "ADMINISTRADOR" && (
              <Link
                to="/usuarios"
                className="rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-cyan-800"
              >
                Usuarios
              </Link>
            )}
            <NotificationCenter csrfToken={session.csrf_token} />
            <Link
              to="/cambiar-password"
              className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              Cambiar contraseña
            </Link>
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

        {esAuditor ? (
          <>
            <p className="text-sm font-semibold text-cyan-800">
              Auditor / Directivo · Consulta global
            </p>
            <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">
              Dashboard de auditoría
            </h1>
            <div className="mt-8">
              <Suspense fallback={<p role="status">Cargando dashboard…</p>}>
                <DashboardAuditor />
              </Suspense>
            </div>
          </>
        ) : (
          <>
            <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
              <div>
                <span className="rounded-full bg-cyan-100 px-3 py-1 text-sm font-semibold text-cyan-900">
                  Sesión activa
                </span>
                <h1 className="mt-5 text-3xl font-bold tracking-tight text-slate-950 sm:text-5xl">
                  Bienvenido a RescueSync
                </h1>
                <p className="mt-4 max-w-2xl text-lg leading-8 text-slate-600">
                  Tu rol es {roleLabels[session.usuario.rol]}.{" "}
                  {responsabilidadesPorRol[session.usuario.rol]}
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
                      {session.usuario.organizacion?.nombre ??
                        "Sin organización"}
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

              {session.usuario.rol === "ADMINISTRADOR" ? (
                <div className="mt-5 grid gap-5 md:grid-cols-2">
                  <article className="rounded-2xl border border-cyan-200 bg-white p-6 shadow-sm">
                    <h3 className="text-xl font-semibold text-slate-950">
                      Gestionar usuarios
                    </h3>
                    <p className="mt-3 max-w-2xl leading-7 text-slate-600">
                      Creá cuentas, actualizá roles y organizaciones, restablecé
                      contraseñas y administrá accesos.
                    </p>
                    <Link
                      to="/usuarios"
                      className="mt-6 inline-flex rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800"
                    >
                      Gestionar usuarios
                    </Link>
                  </article>
                  <article className="rounded-2xl border border-cyan-200 bg-white p-6 shadow-sm">
                    <h3 className="text-xl font-semibold text-slate-950">
                      Gestionar organizaciones
                    </h3>
                    <p className="mt-3 max-w-2xl leading-7 text-slate-600">
                      Registrá municipios, centros coordinadores y ONG para
                      asignarlos a sus usuarios.
                    </p>
                    <Link
                      to="/organizaciones"
                      className="mt-6 inline-flex rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800"
                    >
                      Gestionar organizaciones
                    </Link>
                  </article>
                  <article className="rounded-2xl border border-cyan-200 bg-white p-6 shadow-sm">
                    <h3 className="text-xl font-semibold text-slate-950">
                      Catálogo nacional
                    </h3>
                    <p className="mt-3 leading-7 text-slate-600">
                      Consultá las capacidades disponibles y registrá nuevas
                      capacidades usando las unidades predefinidas.
                    </p>
                    <Link
                      to="/catalogo-nacional"
                      className="mt-6 inline-flex rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800"
                    >
                      Gestionar capacidades
                    </Link>
                  </article>
                </div>
              ) : esMunicipio ? (
                <div className="mt-5 grid gap-5 md:grid-cols-2">
                  <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h3 className="text-xl font-semibold text-slate-950">
                      Registrar emergencia
                    </h3>
                    <p className="mt-3 leading-7 text-slate-600">
                      Informá la gravedad, la zona afectada y la descripción
                      inicial de una nueva emergencia de tu municipio.
                    </p>
                    <Link
                      to="/emergencias/nueva"
                      className="mt-6 inline-flex rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700"
                    >
                      Registrar emergencia
                    </Link>
                  </article>
                  <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h3 className="text-xl font-semibold text-slate-950">
                      Mis emergencias
                    </h3>
                    <p className="mt-3 leading-7 text-slate-600">
                      Consultá las emergencias de tu municipio, revisá su estado
                      y reintentá la vinculación cuando sea necesario.
                    </p>
                    <Link
                      to="/mis-emergencias"
                      className="mt-6 inline-flex rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700"
                    >
                      Ver mis emergencias
                    </Link>
                  </article>
                </div>
              ) : esCoordinador ? (
                <div className="mt-5">
                  <BandejaEmergencias rol="COORDINADOR_REGIONAL" />
                </div>
              ) : esOng ? (
                <div className="mt-5 grid gap-5 md:grid-cols-2">
                  <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h3 className="text-xl font-semibold text-slate-950">
                      Mis recursos
                    </h3>
                    <p className="mt-3 leading-7 text-slate-600">
                      Registrá recursos y actualizá el inventario nacional de tu
                      ONG y consultá sus certificaciones y capacidades
                      habilitadas.
                    </p>
                    <Link
                      to="/mis-recursos"
                      className="mt-6 inline-flex rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800"
                    >
                      Gestionar mis recursos
                    </Link>
                  </article>
                  <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h3 className="text-xl font-semibold text-slate-950">
                      Convocatorias abiertas
                    </h3>
                    <p className="mt-3 leading-7 text-slate-600">
                      Consultá las convocatorias vigentes y los lotes publicados
                      en cada una.
                    </p>
                    <Link
                      to="/convocatorias"
                      className="mt-6 inline-flex rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800"
                    >
                      Ver convocatorias
                    </Link>
                  </article>
                  <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h3 className="text-xl font-semibold text-slate-950">
                      Mis ofertas
                    </h3>
                    <p className="mt-3 leading-7 text-slate-600">
                      Revisá las ofertas que presentaste y su estado.
                    </p>
                    <Link
                      to="/mis-ofertas"
                      className="mt-6 inline-flex rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800"
                    >
                      Ver mis ofertas
                    </Link>
                  </article>
                  <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h3 className="text-xl font-semibold text-slate-950">
                      Presentar oferta
                    </h3>
                    <p className="mt-3 leading-7 text-slate-600">
                      Recursos y personal para uno o más lotes publicados.
                    </p>
                    <Link
                      to="/ofertas/nueva"
                      className="mt-6 inline-flex rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800"
                    >
                      Crear oferta
                    </Link>
                  </article>
                </div>
              ) : null}
            </section>
          </>
        )}
      </section>
    </main>
  );
}
