import { lazy, Suspense, type ReactElement } from "react";
import { Link } from "react-router";

import { AppHeader } from "../components/AppHeader";
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
  const esMunicipio = session.usuario.rol === "OPERADOR_MUNICIPAL";
  const esCoordinador = session.usuario.rol === "COORDINADOR_REGIONAL";
  const esOng = session.usuario.rol === "REPRESENTANTE_ONG";
  const esAuditor = session.usuario.rol === "AUDITOR_DIRECTIVO";

  return (
    <main className="min-h-screen bg-slate-50">
      <AppHeader session={session} />

      <section className="mx-auto max-w-6xl px-5 py-12 sm:px-6 sm:py-16">
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
                      className="action-button action-primary mt-6"
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
                      className="action-button action-primary mt-6"
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
                      className="action-button action-primary mt-6"
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
                      className="action-button action-primary mt-6"
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
                      className="action-button action-primary mt-6"
                    >
                      Ver mis emergencias
                    </Link>
                  </article>
                </div>
              ) : esCoordinador ? (
                <div className="mt-5 grid gap-5 md:grid-cols-2">
                  <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h3 className="text-xl font-semibold text-slate-950">
                      Emergencias pendientes
                    </h3>
                    <p className="mt-3 leading-7 text-slate-600">
                      Revisá las emergencias que todavía no tienen lotes y
                      organizá sus necesidades para comenzar la coordinación.
                    </p>
                    <Link
                      to="/emergencias/pendientes"
                      className="action-button action-primary mt-6"
                    >
                      Ver emergencias pendientes
                    </Link>
                  </article>
                  <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                    <h3 className="text-xl font-semibold text-slate-950">
                      Emergencias no pendientes
                    </h3>
                    <p className="mt-3 leading-7 text-slate-600">
                      Consultá las emergencias con lotes ya creados y filtrá por
                      estado para seguir su evolución.
                    </p>
                    <Link
                      to="/emergencias/con-lotes"
                      className="action-button action-primary mt-6"
                    >
                      Ver emergencias no pendientes
                    </Link>
                  </article>
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
                      className="action-button action-primary mt-6"
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
                      className="action-button action-primary mt-6"
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
                      className="action-button action-primary mt-6"
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
                      className="action-button action-primary mt-6"
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
