import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";

import App from "./App";
import type { Role, Session } from "./schemas/auth";

const API_URL = "http://localhost:8000/api/v1";
const organizationsByRole: Record<
  Role,
  Session["usuario"]["organizacion"]
> = {
  OPERADOR_MUNICIPAL: {
    id: 3,
    nombre: "Municipio del Delta",
    tipo: "MUNICIPIO",
  },
  COORDINADOR_REGIONAL: {
    id: 4,
    nombre: "Centro Litoral",
    tipo: "CENTRO_COORDINADOR",
  },
  REPRESENTANTE_ONG: {
    id: 5,
    nombre: "Rescate Unido",
    tipo: "ONG",
  },
  AUDITOR_DIRECTIVO: null,
  ADMINISTRADOR: null,
};

function sessionForRole(role: Role, requiresPasswordChange = false): Session {
  return {
    usuario: {
      id: 7,
      email: `${role.toLowerCase()}@rescuesync.org`,
      rol: role,
      organizacion: organizationsByRole[role],
      requiere_cambio_password: requiresPasswordChange,
    },
    csrf_token: "csrf-firmado",
  };
}

const session = sessionForRole("OPERADOR_MUNICIPAL");
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

  it("obliga a reemplazar una contraseña temporal y renueva la sesión", async () => {
    const temporarySession = sessionForRole("ADMINISTRADOR", true);
    const updatedSession = sessionForRole("ADMINISTRADOR");
    let csrfHeader: string | null = null;
    server.use(
      http.post(`${API_URL}/auth/login`, () =>
        HttpResponse.json(temporarySession),
      ),
      http.post(`${API_URL}/auth/password`, async ({ request }) => {
        csrfHeader = request.headers.get("X-CSRF-Token");
        expect(await request.json()).toEqual({
          password_actual: "administrador123",
          password_nueva: "Una-clave-nueva-2026",
        });
        return HttpResponse.json(updatedSession);
      }),
    );
    const user = userEvent.setup();
    renderApp("/login");

    await user.type(
      screen.getByRole("textbox", { name: "Correo electrónico" }),
      "admin@rescuesync.org",
    );
    await user.type(screen.getByLabelText("Contraseña"), "administrador123");
    await user.click(
      screen.getByRole("button", { name: "Ingresar a RescueSync" }),
    );

    expect(
      await screen.findByRole("heading", {
        name: "Creá una contraseña nueva",
      }),
    ).toBeInTheDocument();
    await user.type(
      screen.getByLabelText("Contraseña actual"),
      "administrador123",
    );
    await user.type(
      screen.getByLabelText("Contraseña nueva"),
      "Una-clave-nueva-2026",
    );
    await user.type(
      screen.getByLabelText("Repetir contraseña nueva"),
      "Una-clave-nueva-2026",
    );
    await user.click(
      screen.getByRole("button", { name: "Guardar contraseña" }),
    );

    expect(
      await screen.findByRole("heading", { name: "Bienvenido a RescueSync" }),
    ).toBeInTheDocument();
    expect(csrfHeader).toBe("csrf-firmado");
  });

  it("permite al administrador crear una cuenta temporal", async () => {
    const adminSession = sessionForRole("ADMINISTRADOR");
    let createdPayload: unknown;
    server.use(
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json(adminSession)),
      http.get(`${API_URL}/usuarios`, () => HttpResponse.json([])),
      http.get(`${API_URL}/organizaciones`, () =>
        HttpResponse.json([
          { id: 3, nombre: "Municipio del Delta", tipo: "MUNICIPIO" },
        ]),
      ),
      http.post(`${API_URL}/usuarios`, async ({ request }) => {
        createdPayload = await request.json();
        return HttpResponse.json(
          {
            id: 20,
            email: "nuevo@rescuesync.org",
            rol: "OPERADOR_MUNICIPAL",
            organizacion: {
              id: 3,
              nombre: "Municipio del Delta",
              tipo: "MUNICIPIO",
            },
            activo: true,
            requiere_cambio_password: true,
            creado_en: "2026-09-17T20:00:00Z",
            actualizado_en: "2026-09-17T20:00:00Z",
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderApp("/usuarios");

    expect(
      await screen.findByRole("heading", {
        name: "Administración de usuarios",
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Crear usuario" }),
    ).toBeInTheDocument();
    await user.type(
      screen.getByLabelText("Correo electrónico"),
      "nuevo@rescuesync.org",
    );
    await user.type(
      screen.getByLabelText("Contraseña temporal"),
      "Temporal-2026",
    );
    await user.selectOptions(screen.getByLabelText("Rol"), "OPERADOR_MUNICIPAL");
    await user.selectOptions(screen.getByLabelText("Organización"), "3");
    await user.click(screen.getByRole("button", { name: "Crear usuario" }));

    expect(await screen.findByText(
      "Usuario creado con contraseña temporal.",
    )).toBeInTheDocument();
    expect(createdPayload).toEqual({
      email: "nuevo@rescuesync.org",
      password: "Temporal-2026",
      rol: "OPERADOR_MUNICIPAL",
      organizacion_id: 3,
    });
  });
});

describe("navegación por rol", () => {
  it.each<{
    role: Role;
    visible: string | null;
    hidden: string[];
  }>([
    {
      role: "OPERADOR_MUNICIPAL",
      visible: "Registrar emergencia",
      hidden: ["Generar y publicar lotes", "Presentar oferta"],
    },
    {
      role: "COORDINADOR_REGIONAL",
      visible: "Generar y publicar lotes",
      hidden: ["Registrar emergencia", "Presentar oferta"],
    },
    {
      role: "REPRESENTANTE_ONG",
      visible: "Presentar oferta",
      hidden: ["Registrar emergencia", "Generar y publicar lotes"],
    },
    {
      role: "AUDITOR_DIRECTIVO",
      visible: null,
      hidden: [
        "Registrar emergencia",
        "Generar y publicar lotes",
        "Presentar oferta",
      ],
    },
    {
      role: "ADMINISTRADOR",
      visible: "Gestionar usuarios",
      hidden: [
        "Registrar emergencia",
        "Generar y publicar lotes",
        "Presentar oferta",
      ],
    },
  ])("muestra únicamente las acciones habilitadas para $role", async (testCase) => {
    server.use(
      http.get(`${API_URL}/auth/me`, () =>
        HttpResponse.json(sessionForRole(testCase.role)),
      ),
    );
    renderApp("/");

    expect(
      await screen.findByRole("heading", { name: "Bienvenido a RescueSync" }),
    ).toBeInTheDocument();

    if (testCase.visible === null) {
      expect(
        screen.getByRole("heading", { name: "Perfil preparado para auditoría" }),
      ).toBeInTheDocument();
    } else {
      expect(
        screen.getByRole("heading", { name: testCase.visible }),
      ).toBeInTheDocument();
    }

    for (const hiddenAction of testCase.hidden) {
      expect(
        screen.queryByRole("heading", { name: hiddenAction }),
      ).not.toBeInTheDocument();
    }
  });
});
