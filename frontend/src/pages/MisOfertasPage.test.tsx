import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { MisOfertasPage } from "./MisOfertasPage";

const API_URL = "http://localhost:8000/api/v1";

const oferta = {
  id: 9,
  convocatoria_id: 5,
  emergencia_id: 31,
  ong_creadora_id: 4,
  creada_por_usuario_id: 7,
  estado: "PRESENTADA",
  version_actual: 1,
  observaciones: "Donación inicial",
  presentada_en: "2026-09-19T18:20:39.102766Z",
  creada_en: "2026-09-19T18:20:39.102766Z",
  items: [
    {
      id: 1,
      lote_id: 12,
      tipo: "RECURSO",
      descripcion: "Bidones de agua potable",
      cantidad_ofrecida: "500.000",
      unidad: "litros",
    },
  ],
  emergencia: {
    zona: "Ribera norte",
    gravedad: "ALTA",
    descripcion: "Inundación con familias evacuadas.",
  },
};

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <MisOfertasPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MisOfertasPage", () => {
  it("indica la carga mientras consulta las ofertas", async () => {
    let resolver: ((valor: Response) => void) | undefined;
    const pendiente = new Promise<Response>((resolve) => {
      resolver = resolve;
    });
    server.use(http.get(`${API_URL}/ofertas`, () => pendiente));
    renderPage();

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Cargando tus ofertas…",
    );

    resolver?.(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  it("muestra el estado vacío sin ofertas presentadas", async () => {
    server.use(http.get(`${API_URL}/ofertas`, () => HttpResponse.json([])));
    renderPage();

    expect(
      await screen.findByText("Todavía no presentaste ofertas."),
    ).toBeInTheDocument();
  });

  it("lista las ofertas propias con el contexto de la emergencia, sin ids", async () => {
    server.use(http.get(`${API_URL}/ofertas`, () => HttpResponse.json([oferta])));
    renderPage();

    expect(await screen.findByText("Alta · Ribera norte")).toBeInTheDocument();
    expect(screen.getByText("Presentada")).toBeInTheDocument();
    expect(screen.queryByText(/Oferta N/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Convocatoria N/)).not.toBeInTheDocument();

    await userEvent.setup().click(screen.getByText("Alta · Ribera norte"));

    expect(screen.getByText("Donación inicial")).toBeInTheDocument();
    expect(
      screen.getByText(/Bidones de agua potable — 500\.000 litros \(Recurso\)/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/lote N/)).not.toBeInTheDocument();
  });

  it("muestra el error accionable y permite reintentar", async () => {
    let intentos = 0;
    server.use(
      http.get(`${API_URL}/ofertas`, () => {
        intentos += 1;
        if (intentos === 1) {
          return HttpResponse.json({ detail: "Falla temporal." }, { status: 500 });
        }
        return HttpResponse.json([oferta]);
      }),
    );
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Falla temporal.");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("Alta · Ribera norte")).toBeInTheDocument();
    expect(intentos).toBe(2);
  });
});
