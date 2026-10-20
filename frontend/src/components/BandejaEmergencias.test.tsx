import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { emergenciasQueryKey } from "../hooks/useEmergencias";
import type { EmergenciaEnBandeja } from "../schemas/emergencia";
import { BandejaEmergencias } from "./BandejaEmergencias";

const API_URL = "http://localhost:8000/api/v1";

const emergenciaBase = {
  id: 31,
  municipio_id: 1,
  centro_coordinador_id: null,
  creada_por_usuario_id: 1,
  gravedad: "ALTA",
  zona: "Ribera norte",
  descripcion: "Inundación con familias evacuadas y acceso restringido.",
  estado: "REGISTRADA",
  tiene_lotes: false,
  bonita_sync: "PENDIENTE",
  bonita_process_instance_id: null,
  bonita_ultimo_error: null,
  bonita_ultimo_intento_en: null,
  creada_en: "2026-09-19T18:20:39.102766Z",
  actualizada_en: "2026-09-19T18:20:39.102766Z",
} satisfies EmergenciaEnBandeja;

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderBandeja(
  rol: "OPERADOR_MUNICIPAL" | "COORDINADOR_REGIONAL",
  csrfToken?: string,
  emergenciasEnCache?: EmergenciaEnBandeja[],
): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  if (emergenciasEnCache !== undefined) {
    queryClient.setQueryData(
      [...emergenciasQueryKey, "bandeja", rol === "COORDINADOR_REGIONAL" ? false : undefined, undefined, "paginas"],
      { pages: [{ items: emergenciasEnCache, siguiente: undefined }], pageParams: [0] },
    );
  }
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <BandejaEmergencias rol={rol} csrfToken={csrfToken} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BandejaEmergencias", () => {
  it("indica la carga mientras consulta la bandeja", async () => {
    let resolver: ((valor: Response) => void) | undefined;
    const pendiente = new Promise<Response>((resolve) => {
      resolver = resolve;
    });
    server.use(http.get(`${API_URL}/emergencias`, () => pendiente));
    renderBandeja("OPERADOR_MUNICIPAL");

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Cargando emergencias…",
    );

    resolver?.(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await waitFor(() => {
      expect(screen.getByText("Todavía no registraste emergencias.")).toBeInTheDocument();
    });
  });

  it("muestra el estado vacío para un municipio sin emergencias", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () => HttpResponse.json([], { status: 200 })),
    );
    renderBandeja("OPERADOR_MUNICIPAL");

    expect(
      await screen.findByText("Todavía no registraste emergencias."),
    ).toBeInTheDocument();
  });

  it("muestra el estado vacío para un centro coordinador sin pendientes", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () => HttpResponse.json([], { status: 200 })),
    );
    renderBandeja("COORDINADOR_REGIONAL");

    expect(
      await screen.findByText("No hay emergencias pendientes sin lotes."),
    ).toBeInTheDocument();
  });

  it("retira una emergencia publicada de la bandeja en caché del coordinador", async () => {
    renderBandeja("COORDINADOR_REGIONAL", undefined, [
      { ...emergenciaBase, estado: "PUBLICADA", tiene_lotes: true },
    ]);

    expect(
      await screen.findByText("No hay emergencias pendientes sin lotes."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Alta · Ribera norte")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Generar lotes" }),
    ).not.toBeInTheDocument();
  });

  it("lista las emergencias devueltas con su estado y gravedad", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json(
          [
            emergenciaBase,
            { ...emergenciaBase, id: 32, zona: "Corredor Norte", gravedad: "MEDIA", estado: "EN_COORDINACION" },
          ],
          { status: 200 },
        ),
      ),
    );
    renderBandeja("OPERADOR_MUNICIPAL");

    expect(await screen.findByText("Alta · Ribera norte")).toBeInTheDocument();
    expect(screen.getByText("Registrada")).toBeInTheDocument();
    expect(screen.getByText("Media · Corredor Norte")).toBeInTheDocument();
    expect(screen.getByText("En coordinación")).toBeInTheDocument();
  });

  it("muestra el detalle de una emergencia al expandirla", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json([emergenciaBase], { status: 200 }),
      ),
    );
    const user = userEvent.setup();
    renderBandeja("OPERADOR_MUNICIPAL");

    const resumen = await screen.findByText("Alta · Ribera norte");
    expect(
      screen.queryByText(
        "Inundación con familias evacuadas y acceso restringido.",
      ),
    ).not.toBeVisible();

    await user.click(resumen);

    expect(
      screen.getByText("Inundación con familias evacuadas y acceso restringido."),
    ).toBeVisible();
  });

  it("muestra el error de Bonita y permite reintentar la vinculación", async () => {
    let csrfHeader: string | null = null;
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json(
          [
            {
              ...emergenciaBase,
              bonita_sync: "ERROR",
              bonita_ultimo_error: "Bonita no está disponible.",
              bonita_ultimo_intento_en: "2026-09-28T16:00:00Z",
            },
          ],
          { status: 200 },
        ),
      ),
      http.post(
        `${API_URL}/emergencias/31/reintentar-bonita`,
        ({ request }) => {
          csrfHeader = request.headers.get("X-CSRF-Token");
          return HttpResponse.json(
            {
              ...emergenciaBase,
              bonita_sync: "VINCULADA",
              bonita_process_instance_id: 4242,
              bonita_ultimo_error: null,
              bonita_ultimo_intento_en: "2026-09-28T16:01:00Z",
            },
            { status: 200 },
          );
        },
      ),
    );
    const user = userEvent.setup();
    renderBandeja("OPERADOR_MUNICIPAL", "csrf-firmado");

    await user.click(await screen.findByText("Alta · Ribera norte"));
    expect(screen.getByText("Error de vinculación")).toBeVisible();
    expect(screen.getByText("Bonita no está disponible.")).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Vincular con Bonita" }),
    );

    expect(
      await screen.findByText("Vinculada con Bonita"),
    ).toBeInTheDocument();
    expect(csrfHeader).toBe("csrf-firmado");
  });

  it("ofrece generar lotes solo al centro coordinador", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json([emergenciaBase], { status: 200 }),
      ),
    );
    const user = userEvent.setup();
    renderBandeja("COORDINADOR_REGIONAL");

    await user.click(await screen.findByText("Alta · Ribera norte"));

    expect(screen.getByRole("link", { name: "Generar lotes" })).toHaveAttribute(
      "href",
      "/emergencias/31/lotes",
    );
  });

  it("no ofrece generar lotes al municipio", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json([emergenciaBase], { status: 200 }),
      ),
    );
    const user = userEvent.setup();
    renderBandeja("OPERADOR_MUNICIPAL");

    await user.click(await screen.findByText("Alta · Ribera norte"));

    expect(
      screen.queryByRole("link", { name: "Generar lotes" }),
    ).not.toBeInTheDocument();
  });

  it("muestra el error accionable cuando falla la consulta", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json(
          { detail: "Solo un municipio activo puede consultar sus emergencias." },
          { status: 403 },
        ),
      ),
    );
    renderBandeja("OPERADOR_MUNICIPAL");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Solo un municipio activo puede consultar sus emergencias.",
    );
  });

  it("reintenta la consulta al usar el botón de reintentar", async () => {
    let intentos = 0;
    server.use(
      http.get(`${API_URL}/emergencias`, () => {
        intentos += 1;
        if (intentos === 1) {
          return HttpResponse.json({ detail: "Falla temporal." }, { status: 500 });
        }
        return HttpResponse.json([emergenciaBase], { status: 200 });
      }),
    );
    const user = userEvent.setup();
    renderBandeja("OPERADOR_MUNICIPAL");

    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("Alta · Ribera norte")).toBeInTheDocument();
    expect(intentos).toBe(2);
  });
});
