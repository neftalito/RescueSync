import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import { DashboardAuditor } from "./DashboardAuditor";
import type { ReporteMetricas, ReporteTiempos } from "../schemas/metricas";

const base = "http://localhost:8000/api/v1";
const filtros = {
  fecha_desde: "2026-10-01",
  fecha_hasta: "2026-10-15",
  municipio_id: null,
  gravedad: null,
  estado: null,
};
const locales: ReporteMetricas = {
  generado_en: "2026-10-15T12:00:00Z",
  filtros,
  municipios: [{ id: 1, nombre: "Municipio del Delta" }],
  resumen: {
    emergencias: 2,
    activas: 1,
    resueltas: 1,
    convocatorias_abiertas: 1,
    ofertas_presentadas: 3,
    ong_participantes: 2,
  },
  por_estado: [
    { categoria: "RESUELTA", cantidad: 1 },
    { categoria: "PUBLICADA", cantidad: 1 },
  ],
  por_gravedad: [{ categoria: "ALTA", cantidad: 2 }],
  evolucion_mensual: [{ categoria: "2026-10", cantidad: 2 }],
  tipos_oferta: [
    { categoria: "INDIVIDUAL", cantidad: 2 },
    { categoria: "CONJUNTA", cantidad: 1 },
  ],
  cantidades_ofrecidas: [
    {
      capacidad: "Agua",
      codigo_capacidad: "AGUA",
      cantidad: "3000.000",
      unidad: "litros",
    },
  ],
};
const tiempos: ReporteTiempos = {
  generado_en: "2026-10-15T12:00:00Z",
  filtros,
  disponibilidad: "PARCIAL",
  casos_seleccionados: 2,
  casos_vinculados: 2,
  casos_consultados: 1,
  casos_con_muestras: 1,
  casos_sin_historial_suficiente: 0,
  casos_con_error: 1,
  muestras_descartadas: 0,
  etapas: [
    {
      etapa: "Generar lotes",
      version_proceso: "1.2",
      promedio_segundos: 3600,
      muestras: 2,
    },
  ],
};
const server = setupServer(
  http.get(`${base}/metricas`, () => HttpResponse.json(locales)),
  http.get(`${base}/metricas/tiempos`, () => HttpResponse.json(tiempos)),
);
beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    },
  );
});
afterEach(() => {
  cleanup();
  server.resetHandlers();
  vi.restoreAllMocks();
});
afterAll(() => {
  server.close();
  vi.unstubAllGlobals();
});

function mostrar(): void {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <DashboardAuditor />
    </QueryClientProvider>,
  );
}

describe("dashboard del auditor", () => {
  it("muestra indicadores, gráficos, muestras y limitaciones", async () => {
    mostrar();
    expect(
      await screen.findByText("Cantidades ofrecidas por capacidad"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Emergencias por estado" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("Historial parcial")).toBeInTheDocument();
    expect(
      screen.getByRole("table", { name: "Promedios y muestras de Bonita" }),
    ).toHaveTextContent("Generar lotes");
    expect(
      screen.getAllByText("No disponible: requiere adjudicación y cierre"),
    ).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Exportar" })).toBeEnabled();
  });

  it("valida fechas antes de consultar y envía todos los filtros aplicados con sesión", async () => {
    let ultimaUrl: URL | undefined;
    let credenciales: RequestCredentials | undefined;
    server.use(
      http.get(`${base}/metricas`, ({ request }) => {
        ultimaUrl = new URL(request.url);
        credenciales = request.credentials;
        return HttpResponse.json(locales);
      }),
    );
    const user = userEvent.setup();
    mostrar();
    await screen.findByText("Cantidades ofrecidas por capacidad");
    await user.clear(screen.getByLabelText("Desde"));
    await user.type(screen.getByLabelText("Desde"), "2026-11-01");
    await user.clear(screen.getByLabelText("Hasta"));
    await user.type(screen.getByLabelText("Hasta"), "2026-10-31");
    await user.click(screen.getByRole("button", { name: "Aplicar filtros" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La fecha desde debe ser anterior",
    );
    await user.clear(screen.getByLabelText("Desde"));
    await user.type(screen.getByLabelText("Desde"), "2026-10-01");
    await user.selectOptions(screen.getByLabelText("Municipio"), "1");
    await user.selectOptions(screen.getByLabelText("Gravedad"), "ALTA");
    await user.selectOptions(screen.getByLabelText("Estado"), "PUBLICADA");
    await user.click(screen.getByRole("button", { name: "Aplicar filtros" }));
    await waitFor(() =>
      expect(ultimaUrl?.searchParams.get("estado")).toBe("PUBLICADA"),
    );
    expect(ultimaUrl?.searchParams.get("municipio_id")).toBe("1");
    expect(ultimaUrl?.searchParams.get("gravedad")).toBe("ALTA");
    expect(credenciales).toBe("include");
  });

  it("mantiene métricas locales y exportación cuando falla Bonita", async () => {
    server.use(
      http.get(`${base}/metricas/tiempos`, () =>
        HttpResponse.json({ detail: "Sin conexión" }, { status: 503 }),
      ),
    );
    mostrar();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Las métricas locales siguen disponibles",
    );
    expect(
      await screen.findByText("Cantidades ofrecidas por capacidad"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exportar" })).toBeEnabled();
  });

  it("permite reintentar el resumen y muestra un período vacío", async () => {
    server.use(
      http.get(`${base}/metricas`, () =>
        HttpResponse.json({ detail: "Sin conexión local" }, { status: 503 }),
      ),
    );
    const user = userEvent.setup();
    mostrar();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Sin conexión local",
    );
    expect(screen.getByRole("button", { name: "Exportar" })).toBeDisabled();
    server.use(
      http.get(`${base}/metricas`, () =>
        HttpResponse.json({
          ...locales,
          resumen: {
            emergencias: 0,
            activas: 0,
            resueltas: 0,
            convocatorias_abiertas: 0,
            ofertas_presentadas: 0,
            ong_participantes: 0,
          },
          cantidades_ofrecidas: [],
        }),
      ),
    );
    await user.click(
      screen.getByRole("button", { name: "Reintentar métricas" }),
    );
    expect(
      await screen.findByText(
        "No hay emergencias para los filtros seleccionados.",
      ),
    ).toBeInTheDocument();
  });

  it("descarga CSV y JSON del mismo reporte sin volver a consultar Bonita", async () => {
    let consultas = 0;
    server.use(
      http.get(`${base}/metricas/tiempos`, () => {
        consultas++;
        return HttpResponse.json(tiempos);
      }),
    );
    const blobs: Blob[] = [];
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn((blob: Blob) => {
        blobs.push(blob);
        return "blob:reporte";
      }),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    const user = userEvent.setup();
    mostrar();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Exportar" })).toBeEnabled(),
    );
    await user.click(screen.getByRole("button", { name: "Exportar" }));
    await user.click(screen.getByRole("button", { name: "Exportar JSON" }));
    await user.click(screen.getByRole("button", { name: "Exportar" }));
    await user.click(screen.getByRole("button", { name: "Exportar CSV" }));
    expect(click).toHaveBeenCalledTimes(2);
    expect(blobs.map((b) => b.type)).toEqual([
      "application/json;charset=utf-8",
      "text/csv;charset=utf-8",
    ]);
    expect(consultas).toBe(1);
  });
});
