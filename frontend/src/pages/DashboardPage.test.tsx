import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { DashboardPage } from "./DashboardPage";
import type { Session } from "../schemas/auth";

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
  it("presenta las funcionalidades municipales como tarjetas con enlaces a vistas separadas", () => {
    renderDashboard();

    expect(
      screen.getByRole("heading", { name: "Registrar emergencia" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Registrar emergencia" }),
    ).toHaveAttribute("href", "/emergencias/nueva");
    expect(
      screen.getByRole("heading", { name: "Mis emergencias" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Ver mis emergencias" }),
    ).toHaveAttribute("href", "/mis-emergencias");
    expect(screen.queryByLabelText("Zona afectada")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Registrar emergencia" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Cargando emergencias…")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Todavía no registraste emergencias."),
    ).not.toBeInTheDocument();
  });
});
