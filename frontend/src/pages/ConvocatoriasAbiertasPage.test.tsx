import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { ConvocatoriasAbiertasPage } from "./ConvocatoriasAbiertasPage";

const API_URL = "http://localhost:8000/api/v1";

const convocatoria = {
  id: 5,
  emergencia_id: 31,
  numero: 1,
  estado: "ABIERTA",
  publicada_en: "2026-09-19T18:20:39.102766Z",
  cierra_en: "2026-09-20T18:20:39.102766Z",
  lotes: [
    { lote_id: 12, cantidad_publicada: "1000.000", unidad_publicada: "litros" },
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
        <ConvocatoriasAbiertasPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ConvocatoriasAbiertasPage", () => {
  it("indica la carga mientras consulta las convocatorias", async () => {
    let resolver: ((valor: Response) => void) | undefined;
    const pendiente = new Promise<Response>((resolve) => {
      resolver = resolve;
    });
    server.use(http.get(`${API_URL}/convocatorias`, () => pendiente));
    renderPage();

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Cargando convocatorias…",
    );

    resolver?.(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  it("muestra el estado vacío sin convocatorias abiertas", async () => {
    server.use(
      http.get(`${API_URL}/convocatorias`, () => HttpResponse.json([])),
    );
    renderPage();

    expect(
      await screen.findByText("No hay convocatorias abiertas por el momento."),
    ).toBeInTheDocument();
  });

  it("lista las convocatorias abiertas con sus lotes y un enlace a ver lotes", async () => {
    server.use(
      http.get(`${API_URL}/convocatorias`, () =>
        HttpResponse.json([convocatoria]),
      ),
    );
    renderPage();

    expect(
      await screen.findByText("Convocatoria N.º 1"),
    ).toBeInTheDocument();
    expect(screen.getByText("Alta · Ribera norte")).toBeInTheDocument();
    expect(
      screen.getByText("Inundación con familias evacuadas."),
    ).toBeInTheDocument();
    expect(screen.getByText("1 lote publicado")).toBeInTheDocument();
    expect(screen.getByText(/1000\.000 litros/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver lotes" })).toHaveAttribute(
      "href",
      "/emergencias/31/lotes",
    );
  });

  it("muestra el error accionable y permite reintentar", async () => {
    let intentos = 0;
    server.use(
      http.get(`${API_URL}/convocatorias`, () => {
        intentos += 1;
        if (intentos === 1) {
          return HttpResponse.json({ detail: "Falla temporal." }, { status: 500 });
        }
        return HttpResponse.json([convocatoria]);
      }),
    );
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Falla temporal.");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("Convocatoria N.º 1")).toBeInTheDocument();
    expect(intentos).toBe(2);
  });
});
