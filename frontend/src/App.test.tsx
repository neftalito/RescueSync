import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";

import App from "./App";

const API_URL = "http://localhost:8000/api/v1";
const session = {
  usuario: {
    id: 7,
    email: "operador@municipio.org",
    rol: "OPERADOR_MUNICIPAL" as const,
    organizacion: {
      id: 3,
      nombre: "Municipio del Delta",
      tipo: "MUNICIPIO" as const,
    },
  },
  csrf_token: "csrf-firmado",
};
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderApp(path: string): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("autenticación", () => {
  it("valida y envía el login antes de mostrar la sesión", async () => {
    let requestCredentials: RequestCredentials | undefined;
    server.use(
      http.post(`${API_URL}/auth/login`, async ({ request }) => {
        requestCredentials = request.credentials;
        expect(await request.json()).toEqual({
          email: "operador@municipio.org",
          password: "Una-clave-segura",
        });
        return HttpResponse.json(session);
      }),
    );
    const user = userEvent.setup();
    renderApp("/login");

    await user.type(
      screen.getByRole("textbox", { name: "Correo electrónico" }),
      "operador@municipio.org",
    );
    await user.type(screen.getByLabelText("Contraseña"), "Una-clave-segura");
    await user.click(
      screen.getByRole("button", { name: "Ingresar a RescueSync" }),
    );

    expect(
      await screen.findByRole("heading", { name: "Bienvenido a RescueSync" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Municipio del Delta")).toBeInTheDocument();
    expect(screen.getAllByText("Operador municipal")).toHaveLength(2);
    expect(requestCredentials).toBe("include");
  });

  it("muestra validaciones accesibles sin enviar datos incompletos", async () => {
    const user = userEvent.setup();
    renderApp("/login");

    await user.click(
      screen.getByRole("button", { name: "Ingresar a RescueSync" }),
    );

    expect(await screen.findAllByText(/Ingresá tu/)).toHaveLength(2);
    expect(screen.getByLabelText("Correo electrónico")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("presenta el error accionable del backend", async () => {
    server.use(
      http.post(`${API_URL}/auth/login`, () =>
        HttpResponse.json(
          { detail: "El correo o la contraseña son incorrectos." },
          { status: 401 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderApp("/login");

    await user.type(
      screen.getByRole("textbox", { name: "Correo electrónico" }),
      "operador@municipio.org",
    );
    await user.type(screen.getByLabelText("Contraseña"), "incorrecta");
    await user.click(
      screen.getByRole("button", { name: "Ingresar a RescueSync" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "El correo o la contraseña son incorrectos.",
    );
  });

  it("redirige al login cuando no hay una sesión vigente", async () => {
    server.use(
      http.get(`${API_URL}/auth/me`, () =>
        HttpResponse.json(
          { detail: "La sesión no es válida o expiró." },
          { status: 401 },
        ),
      ),
    );
    renderApp("/");

    expect(
      await screen.findByRole("heading", { name: "Iniciá sesión" }),
    ).toBeInTheDocument();
  });

  it("cierra la sesión con CSRF y vuelve al login", async () => {
    let csrfHeader: string | null = null;
    let requestCredentials: RequestCredentials | undefined;
    server.use(
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json(session)),
      http.post(`${API_URL}/auth/logout`, ({ request }) => {
        csrfHeader = request.headers.get("X-CSRF-Token");
        requestCredentials = request.credentials;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderApp("/");

    await user.click(
      await screen.findByRole("button", { name: "Cerrar sesión" }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Iniciá sesión" }),
      ).toBeInTheDocument();
    });
    expect(csrfHeader).toBe("csrf-firmado");
    expect(requestCredentials).toBe("include");
  });
});
