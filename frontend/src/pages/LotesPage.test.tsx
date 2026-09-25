import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import type { Session } from "../schemas/auth";
import { LotesPage } from "./LotesPage";

const API_URL = "http://localhost:8000/api/v1";

const session: Session = {
  usuario: {
    id: 2,
    email: "coordinador@rescuesync.local",
    rol: "COORDINADOR_REGIONAL",
    organizacion: { id: 3, nombre: "Centro Norte", tipo: "CENTRO_COORDINADOR" },
    requiere_cambio_password: false,
  },
  csrf_token: "csrf-firmado",
};

const emergencia = {
  id: 31,
  municipio_id: 1,
  centro_coordinador_id: null,
  creada_por_usuario_id: 1,
  gravedad: "ALTA",
  zona: "Ribera norte",
  descripcion: "Inundación con familias evacuadas.",
  estado: "REGISTRADA",
  bonita_sync: "VINCULADA",
  bonita_process_instance_id: 1001,
  creada_en: "2026-09-19T18:20:39.102766Z",
  actualizada_en: "2026-09-19T18:20:39.102766Z",
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
            element={<LotesPage session={session} />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LotesPage", () => {
  it("muestra el detalle de la emergencia junto al formulario de lotes", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () => HttpResponse.json([emergencia])),
      http.get(`${API_URL}/emergencias/31/lotes`, () => HttpResponse.json([])),
    );
    renderPage("/emergencias/31/lotes");

    expect(
      await screen.findByRole("heading", { name: "Ribera norte" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Inundación con familias evacuadas."),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "Guardar borrador" }),
    ).toBeInTheDocument();
  });

  it("carga los borradores guardados para editarlos", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () => HttpResponse.json([emergencia])),
      http.get(`${API_URL}/emergencias/31/lotes`, () =>
        HttpResponse.json([
          {
            id: 7,
            emergencia_id: 31,
            creado_por_usuario_id: 2,
            tipo_necesidad: "Agua potable",
            descripcion: "Bidones de 5 litros",
            cantidad_requerida: "500.000",
            unidad: "litros",
            estado: "BORRADOR",
            version: 1,
            creado_en: "2026-09-19T18:20:39.102766Z",
            actualizado_en: "2026-09-19T18:20:39.102766Z",
          },
        ]),
      ),
    );
    renderPage("/emergencias/31/lotes");

    expect(await screen.findByLabelText("Tipo de necesidad")).toHaveValue(
      "Agua potable",
    );
    expect(screen.getByLabelText("Descripción (opcional)")).toHaveValue(
      "Bidones de 5 litros",
    );
  });

  it("muestra el error al consultar los lotes con opción de reintentar", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () => HttpResponse.json([emergencia])),
      http.get(`${API_URL}/emergencias/31/lotes`, () =>
        HttpResponse.json(
          { detail: "Solo el centro coordinador asignado consulta estos lotes." },
          { status: 403 },
        ),
      ),
    );
    renderPage("/emergencias/31/lotes");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Solo el centro coordinador asignado consulta estos lotes.",
    );
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Guardar borrador" }),
    ).not.toBeInTheDocument();
  });

  it("avisa si la emergencia no está en la bandeja del coordinador", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () => HttpResponse.json([emergencia])),
    );
    renderPage("/emergencias/99/lotes");

    expect(
      await screen.findByText(/no está disponible en tu bandeja/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Guardar borrador" }),
    ).not.toBeInTheDocument();
  });

  it("rechaza un identificador inválido", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () => HttpResponse.json([emergencia])),
    );
    renderPage("/emergencias/abc/lotes");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "El identificador de emergencia no es válido.",
    );
  });

  it("muestra el error de la API con opción de reintentar", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json({ detail: "Tu sesión expiró." }, { status: 401 }),
      ),
    );
    renderPage("/emergencias/31/lotes");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Tu sesión expiró.",
    );
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });
});
