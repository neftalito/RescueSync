import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
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
const filtros: ReporteMetricas["filtros"] = {
  fecha_desde: "2026-10-01",
  fecha_hasta: "2026-10-15",
  municipio_id: null,
  gravedad: null,
  estado: null,
  umbral_aportes_horas: 24,
  umbral_resolucion_horas: 72,
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
  indicadores_proceso: {
    emergencias_con_hechos: 1,
    emergencias_sin_hechos: 1,
    resolucion_por_gravedad: [],
    reiteradas: [],
    ranking_ongs: [],
    cobertura_cierres: { total: 0, parcial: 0, proporcion_total: null, proporcion_parcial: null, sin_evidencia: 1 },
    demanda_rubros: [],
    suministros_movilizados: {
      cantidades: [],
      participaciones_con_registro: 0,
      participaciones_sin_registro: 1,
    },
    resolucion_consorcios: { con_consorcio: 0, con_adjudicacion_verificable: 0, sin_adjudicacion_verificable: 1, proporcion: null },
    alerta_adjudicacion_muestras: 0,
    alerta_adjudicacion_promedio_segundos: null,
    definiciones: [],
  },
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
    expect(screen.getByRole("heading", { name: "Suministros movilizados" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Resolución mediante consorcios" })).toBeInTheDocument();
    expect(screen.getByText(/Sin cantidades movilizadas declaradas/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Exportar" })).toBeEnabled();
  });

  it("muestra cantidades ofrecidas, incluido cero, con dos decimales", async () => {
    server.use(
      http.get(`${base}/metricas`, () => HttpResponse.json({
        ...locales,
        cantidades_ofrecidas: [
          ...locales.cantidades_ofrecidas,
          { capacidad: "Alimentos", codigo_capacidad: null, cantidad: "0.000", unidad: "kg" },
        ],
      })),
    );
    mostrar();

    expect(await screen.findByRole("cell", { name: "3.000,00" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "0,00" })).toBeInTheDocument();
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

  it("aplica dos umbrales independientes sin volver a consultar Bonita", async () => {
    const peticionesLocales: URLSearchParams[] = [];
    const peticionesBonita: URLSearchParams[] = [];
    server.use(
      http.get(`${base}/metricas`, ({ request }) => {
        peticionesLocales.push(new URL(request.url).searchParams);
        return HttpResponse.json(locales);
      }),
      http.get(`${base}/metricas/tiempos`, ({ request }) => {
        peticionesBonita.push(new URL(request.url).searchParams);
        return HttpResponse.json(tiempos);
      }),
    );
    const user = userEvent.setup();
    mostrar();
    await screen.findByText("Historial parcial");
    const aportes = screen.getByRole("combobox", { name: "Umbral de finalización de aportes" });
    const resolucion = screen.getByRole("combobox", { name: "Umbral de resolución de emergencias" });
    const opciones = ["8 h", "12 h", "24 h", "48 h", "72 h", "1 semana", "1 mes (30 días)"];
    for (const selector of [aportes, resolucion])
      expect(within(selector).getAllByRole("option").map(opcion => opcion.textContent)).toEqual(opciones);
    expect(aportes).toHaveValue("24");
    expect(resolucion).toHaveValue("72");
    await user.selectOptions(aportes, "168");
    await user.selectOptions(resolucion, "720");
    expect(peticionesLocales).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Aplicar filtros" }));
    await waitFor(() => expect(peticionesLocales).toHaveLength(2));
    expect(peticionesLocales.at(-1)?.get("umbral_aportes_horas")).toBe("168");
    expect(peticionesLocales.at(-1)?.get("umbral_resolucion_horas")).toBe("720");
    expect(peticionesBonita).toHaveLength(1);
    expect(peticionesBonita[0]?.has("umbral_aportes_horas")).toBe(false);
    expect(peticionesBonita[0]?.has("umbral_resolucion_horas")).toBe(false);
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
