import { useEffect, useState, type ReactElement } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

interface Stage {
  actor: string;
  title: string;
  description: string;
}

type ApiStatusValue = "checking" | "online" | "offline";

const stages: Stage[] = [
  {
    actor: "Municipio",
    title: "Registrar emergencia",
    description: "Gravedad, zona afectada y descripción inicial.",
  },
  {
    actor: "Centro coordinador",
    title: "Generar y publicar lotes",
    description: "Necesidades cuantificadas antes de abrir la convocatoria.",
  },
  {
    actor: "ONG",
    title: "Presentar oferta",
    description: "Recursos y personal para uno o más lotes publicados.",
  },
];

function ApiStatus(): ReactElement {
  const [status, setStatus] = useState<ApiStatusValue>("checking");

  useEffect(() => {
    const controller = new AbortController();

    fetch(API_URL + "/health", { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("La API respondió con un error");
        return response.json();
      })
      .then(() => setStatus("online"))
      .catch((error: unknown) => {
        const requestWasAborted =
          error instanceof DOMException && error.name === "AbortError";

        if (!requestWasAborted) setStatus("offline");
      });

    return () => controller.abort();
  }, []);

  const styles: Record<ApiStatusValue, string> = {
    checking: "bg-amber-50 text-amber-700 ring-amber-200",
    online: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    offline: "bg-red-50 text-red-700 ring-red-200",
  };
  const labels: Record<ApiStatusValue, string> = {
    checking: "Comprobando API",
    online: "API disponible",
    offline: "API no disponible",
  };

  let dotStyle = "bg-amber-500";
  if (status === "online") dotStyle = "bg-emerald-500";
  if (status === "offline") dotStyle = "bg-red-500";

  return (
    <span
      className={
        "inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium ring-1 " +
        styles[status]
      }
    >
      <span className="relative flex size-2">
        {status === "checking" && (
          <span className="absolute inline-flex size-full animate-ping rounded-full bg-amber-400 opacity-75" />
        )}
        <span
          className={"relative inline-flex size-2 rounded-full " + dotStyle}
        />
      </span>
      {labels[status]}
    </span>
  );
}

export default function App(): ReactElement {
  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
          <div>
            <p className="text-sm font-semibold tracking-[0.2em] text-blue-700 uppercase">
              RescueSync
            </p>
            <p className="mt-1 text-sm text-slate-500">
              Coordinación regional ante emergencias
            </p>
          </div>
          <ApiStatus />
        </div>
      </header>

      <section className="mx-auto max-w-6xl px-6 py-16">
        <div className="max-w-3xl">
          <span className="rounded-full bg-blue-100 px-3 py-1 text-sm font-medium text-blue-800">
            Entrega 2
          </span>
          <h1 className="mt-6 text-4xl font-bold tracking-tight text-slate-950 sm:text-5xl">
            Flujo inicial de atención de emergencias
          </h1>
          <p className="mt-5 text-lg leading-8 text-slate-600">
            Esta base conecta React, FastAPI y PostgreSQL. El próximo paso es
            implementar los formularios, permisos e integración con Bonita 10.4.
          </p>
        </div>

        <div className="mt-12 grid gap-5 md:grid-cols-3">
          {stages.map((stage, index) => (
            <article
              key={stage.actor}
              className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-blue-700">
                  {stage.actor}
                </span>
                <span className="flex size-8 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-600">
                  {index + 1}
                </span>
              </div>
              <h2 className="mt-8 text-xl font-semibold text-slate-950">
                {stage.title}
              </h2>
              <p className="mt-3 leading-7 text-slate-600">{stage.description}</p>
              <button
                type="button"
                disabled
                className="mt-8 w-full cursor-not-allowed rounded-lg bg-slate-100 px-4 py-2.5 text-sm font-semibold text-slate-400"
              >
                Próximamente
              </button>
            </article>
          ))}
        </div>

        <div className="mt-10 rounded-2xl border border-blue-200 bg-blue-50 p-6 text-blue-950">
          <p className="font-semibold">El entorno base está listo.</p>
          <p className="mt-2 text-sm leading-6 text-blue-800">
            FastAPI publica su documentación interactiva en{" "}
            <a
              className="font-semibold underline underline-offset-4"
              href="http://localhost:8000/docs"
            >
              localhost:8000/docs
            </a>
            .
          </p>
        </div>
      </section>
    </main>
  );
}
