import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { LotesPublicadosPage } from "./LotesPublicadosPage";

const API_URL = "http://localhost:8000/api/v1";

const lotePublicado = {
  id: 12,
  emergencia_id: 31,
  creado_por_usuario_id: 2,
  tipo_necesidad: "Agua potable",
  descripcion: "Bidones de 5 litros",
  cantidad_requerida: "1000.000",
  unidad: "litros",
  estado: "PUBLICADO",
  version: 1,
  creado_en: "2026-09-19T18:20:39.102766Z",
  actualizado_en: "2026-09-19T18:20:39.102766Z",
};

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderPage(ruta: string): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route
            path="/emergencias/:emergenciaId/lotes"
            element={<LotesPublicadosPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LotesPublicadosPage", () => {
  it("indica la carga mientras consulta los lotes", async () => {
    let resolver: ((valor: Response) => void) | undefined;
    const pendiente = new Promise<Response>((resolve) => {
      resolver = resolve;
    });
    server.use(http.get(`${API_URL}/emergencias/31/lotes`, () => pendiente));
    renderPage("/emergencias/31/lotes");

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Cargando lotes…",
    );

    resolver?.(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  it("muestra el estado vacío sin lotes publicados", async () => {
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () => HttpResponse.json([])),
    );
    renderPage("/emergencias/31/lotes");

    expect(
      await screen.findByText("Esta convocatoria todavía no tiene lotes publicados."),
    ).toBeInTheDocument();
  });

  it("lista los lotes publicados con cantidad, unidad y estado", async () => {
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () =>
        HttpResponse.json([lotePublicado]),
      ),
    );
    renderPage("/emergencias/31/lotes");

    expect(await screen.findByText("Agua potable")).toBeInTheDocument();
    expect(screen.getByText("1000.000 litros")).toBeInTheDocument();
    expect(screen.getByText("Publicado")).toBeInTheDocument();
    expect(screen.getByText("Bidones de 5 litros")).toBeInTheDocument();
  });

  it("muestra el error accionable y permite reintentar", async () => {
    let intentos = 0;
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () => {
        intentos += 1;
        if (intentos === 1) {
          return HttpResponse.json({ detail: "Falla temporal." }, { status: 500 });
        }
        return HttpResponse.json([lotePublicado]);
      }),
    );
    const user = userEvent.setup();
    renderPage("/emergencias/31/lotes");

    expect(await screen.findByRole("alert")).toHaveTextContent("Falla temporal.");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("Agua potable")).toBeInTheDocument();
    expect(intentos).toBe(2);
  });

  it("rechaza un identificador de emergencia inválido sin consultar la API", () => {
    server.use(
      http.get(`${API_URL}/emergencias/:id/lotes`, () => {
        throw new Error("no debería consultarse con un id inválido");
      }),
    );
    renderPage("/emergencias/abc/lotes");

    expect(
      screen.getByText("El identificador de emergencia no es válido."),
    ).toBeInTheDocument();
  });
});
