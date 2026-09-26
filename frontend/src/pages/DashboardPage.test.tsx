import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { DashboardPage } from "./DashboardPage";
import type { Session } from "../schemas/auth";

const API_URL = "http://localhost:8000/api/v1";
const CSRF_TOKEN = "csrf-firmado";

const sesionMunicipio: Session = {
  usuario: {
    id: 1,
    email: "municipio@rescuesync.org",
    rol: "OPERADOR_MUNICIPAL",
    organizacion: {
      id: 1,
      nombre: "Municipalidad de Puerto Esperanza",
      tipo: "MUNICIPIO",
    },
    requiere_cambio_password: false,
  },
  csrf_token: CSRF_TOKEN,
};

const emergenciaCreada = {
  id: 31,
  municipio_id: 1,
  centro_coordinador_id: null,
  creada_por_usuario_id: 1,
  gravedad: "ALTA",
  zona: "Ribera norte",
  descripcion: "Inundación con familias evacuadas",
  estado: "REGISTRADA",
  bonita_sync: "PENDIENTE",
  bonita_process_instance_id: null,
  creada_en: "2026-09-19T18:20:39.102766Z",
  actualizada_en: "2026-09-19T18:20:39.102766Z",
  cantidad_lotes_borrador: 0,
};

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderDashboard(): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardPage session={sesionMunicipio} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DashboardPage", () => {
  it("actualiza la bandeja del municipio luego de registrar una emergencia", async () => {
    let listaActual: unknown[] = [];
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json(listaActual, { status: 200 }),
      ),
      http.post(`${API_URL}/emergencias`, () => {
        listaActual = [emergenciaCreada];
        return HttpResponse.json(emergenciaCreada, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderDashboard();

    expect(
      await screen.findByText("Todavía no registraste emergencias."),
    ).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Gravedad"), "ALTA");
    await user.type(screen.getByLabelText("Zona afectada"), "Ribera norte");
    await user.type(
      screen.getByLabelText("Descripción inicial"),
      "Inundación con familias evacuadas",
    );
    await user.click(
      screen.getByRole("button", { name: "Registrar emergencia" }),
    );

    await screen.findByText("Emergencia 31 registrada en estado REGISTRADA.");

    const bandeja = (
      await screen.findByRole("heading", { name: "Mis emergencias" })
    ).closest("section");
    if (bandeja === null) {
      throw new Error("No se encontró la sección de la bandeja de emergencias.");
    }
    expect(
      await within(bandeja).findByText("Alta · Ribera norte"),
    ).toBeInTheDocument();
    expect(
      within(bandeja).queryByText("Todavía no registraste emergencias."),
    ).not.toBeInTheDocument();
  });
});
