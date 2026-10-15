import { type ReactElement } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";
import { MisRecursosPage } from "./pages/MisRecursosPage";

import { ApiError } from "./api/client";
import { useSession } from "./hooks/useSession";
import { useNotificacionesTiempoReal } from "./hooks/useNotificacionesTiempoReal";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { CatalogoNacionalPage } from "./pages/CatalogoNacionalPage";
import { ConvocatoriasAbiertasPage } from "./pages/ConvocatoriasAbiertasPage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { LotesPage } from "./pages/LotesPage";
import { LotesPublicadosPage } from "./pages/LotesPublicadosPage";
import { MisEmergenciasPage } from "./pages/MisEmergenciasPage";
import { MisOfertasPage } from "./pages/MisOfertasPage";
import { NuevaEmergenciaPage } from "./pages/NuevaEmergenciaPage";
import { NuevaOfertaPage } from "./pages/NuevaOfertaPage";
import { OrganizationsPage } from "./pages/OrganizationsPage";
import { UsersPage } from "./pages/UsersPage";

function LoadingScreen(): ReactElement {
  return (
    <main className="grid min-h-screen place-items-center bg-slate-950 px-6 text-white">
      <div className="text-center" role="status">
        <span className="mx-auto block size-10 animate-spin rounded-full border-4 border-white/20 border-t-cyan-400" />
        <p className="mt-4 text-sm font-medium text-slate-300">
          Verificando tu sesión…
        </p>
      </div>
    </main>
  );
}

function ProtectedApp(): ReactElement {
  const session = useSession();
  const location = useLocation();
  const tiempoRealHabilitado =
    session.isSuccess && !session.data.usuario.requiere_cambio_password;
  useNotificacionesTiempoReal(tiempoRealHabilitado);

  if (session.isPending) return <LoadingScreen />;

  if (session.error instanceof ApiError && session.error.status === 401) {
    return <Navigate to="/login" replace />;
  }

  if (session.isError) {
    return (
      <main className="grid min-h-screen place-items-center bg-slate-50 px-6">
        <section className="w-full max-w-md rounded-3xl border border-red-200 bg-white p-8 text-center shadow-sm">
          <p className="text-sm font-bold tracking-[0.16em] text-red-700 uppercase">
            Sin conexión
          </p>
          <h1 className="mt-3 text-2xl font-bold text-slate-950">
            No pudimos verificar tu sesión
          </h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Revisá que la API esté disponible y volvé a intentarlo.
          </p>
          <button
            type="button"
            onClick={() => void session.refetch()}
            className="mt-6 rounded-xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-600"
          >
            Reintentar
          </button>
        </section>
      </main>
    );
  }

  if (
    session.data.usuario.requiere_cambio_password &&
    location.pathname !== "/cambiar-password"
  ) {
    return <Navigate to="/cambiar-password" replace />;
  }

  return (
    <Routes>
      <Route path="/" element={<DashboardPage session={session.data} />} />
      <Route
        path="/emergencias/nueva"
        element={
          session.data.usuario.rol === "OPERADOR_MUNICIPAL" ? (
            <NuevaEmergenciaPage csrfToken={session.data.csrf_token} />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route
        path="/mis-emergencias"
        element={
          session.data.usuario.rol === "OPERADOR_MUNICIPAL" ? (
            <MisEmergenciasPage csrfToken={session.data.csrf_token} />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route
        path="/mis-recursos"
        element={
          session.data.usuario.rol === "REPRESENTANTE_ONG" ? (
            <MisRecursosPage session={session.data} />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route
        path="/cambiar-password"
        element={<ChangePasswordPage session={session.data} />}
      />
      <Route
        path="/usuarios"
        element={
          session.data.usuario.rol === "ADMINISTRADOR" ? (
            <UsersPage session={session.data} />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route
        path="/organizaciones"
        element={
          session.data.usuario.rol === "ADMINISTRADOR" ? (
            <OrganizationsPage session={session.data} />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route
        path="/catalogo-nacional"
        element={
          session.data.usuario.rol === "ADMINISTRADOR" ? (
            <CatalogoNacionalPage session={session.data} />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route
        path="/emergencias/:emergenciaId/lotes"
        element={
          session.data.usuario.rol === "COORDINADOR_REGIONAL" ? (
            <LotesPage session={session.data} />
          ) : session.data.usuario.rol === "REPRESENTANTE_ONG" ? (
            <LotesPublicadosPage />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route
        path="/convocatorias"
        element={
          session.data.usuario.rol === "REPRESENTANTE_ONG" ? (
            <ConvocatoriasAbiertasPage />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route
        path="/mis-ofertas"
        element={
          session.data.usuario.rol === "REPRESENTANTE_ONG" ? (
            <MisOfertasPage />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route
        path="/ofertas/nueva"
        element={
          session.data.usuario.rol === "REPRESENTANTE_ONG" ? (
            <NuevaOfertaPage csrfToken={session.data.csrf_token} />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route
        path="/ofertas/:ofertaId/editar"
        element={
          session.data.usuario.rol === "REPRESENTANTE_ONG" ? (
            <NuevaOfertaPage csrfToken={session.data.csrf_token} />
          ) : (
            <Navigate to="/" replace />
          )
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App(): ReactElement {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/*" element={<ProtectedApp />} />
    </Routes>
  );
}
