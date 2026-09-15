import { type ReactElement } from "react";
import { Navigate, Route, Routes } from "react-router";

import { ApiError } from "./api/client";
import { useSession } from "./hooks/useSession";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";

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

function ProtectedDashboard(): ReactElement {
  const session = useSession();

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

  return <DashboardPage session={session.data} />;
}

export default function App(): ReactElement {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<ProtectedDashboard />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
