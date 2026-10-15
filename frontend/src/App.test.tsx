import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import App from "./App";
import { sessionQueryKey } from "./hooks/useSession";
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
const server = setupServer(
  http.get(`${API_URL}/metricas`, () => HttpResponse.json({ detail: "Sin datos de prueba" }, { status: 503 })),
  http.get(`${API_URL}/metricas/tiempos`, () => HttpResponse.json({ detail: "Sin datos de prueba" }, { status: 503 })),
  http.get(`${API_URL}/emergencias`, () => HttpResponse.json([], { status: 200 })),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderApp(path: string): QueryClient {
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
  return queryClient;
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

  it("permite mostrar y ocultar la contraseña del login con el botón de ojo", async () => {
    const user = userEvent.setup();
    renderApp("/login");

    const password = screen.getByLabelText("Contraseña");
    expect(screen.queryByRole("button", { name: "Mostrar contraseña" })).not.toBeInTheDocument();

    await user.type(password, "Una-clave-segura");
    expect(password).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Mostrar contraseña" }));
    expect(password).toHaveAttribute("type", "text");

    await user.click(screen.getByRole("button", { name: "Ocultar contraseña" }));
    expect(password).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: "Mostrar contraseña" }));
    expect(password).toHaveAttribute("type", "text");
    expect(screen.getByRole("button", { name: "Ocultar contraseña" })).toHaveAttribute("aria-pressed", "true");
    expect(password).toHaveValue("Una-clave-segura");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await user.clear(password);
    expect(screen.queryByRole("button", { name: "Ocultar contraseña" })).not.toBeInTheDocument();
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

    const cerrarSesion = await screen.findByRole("button", { name: "Cerrar sesión" });
    expect(cerrarSesion.textContent).toBe("");
    expect(cerrarSesion.querySelector("svg")).toBeInTheDocument();
    await user.click(cerrarSesion);

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
        name: "Cambiar contraseña",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Opciones", level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Volver al inicio" })).not.toBeInTheDocument();
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

  it("abre Opciones desde el engranaje y cambia la contraseña sin salir de la sección", async () => {
    let csrfHeader: string | null = null;
    let requestCredentials: RequestCredentials | undefined;
    server.use(
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json(session)),
      http.post(`${API_URL}/auth/password`, async ({ request }) => {
        csrfHeader = request.headers.get("X-CSRF-Token");
        requestCredentials = request.credentials;
        expect(await request.json()).toEqual({
          password_actual: "Una-clave-actual",
          password_nueva: "Una-clave-nueva-2026",
        });
        return HttpResponse.json({ ...session, csrf_token: "csrf-renovado" });
      }),
    );
    const user = userEvent.setup();
    const queryClient = renderApp("/");
    const opciones = await screen.findByRole("link", { name: "Opciones" });
    expect(opciones.textContent).toBe("");
    expect(opciones.querySelector("svg")).toBeInTheDocument();
    await user.click(opciones);

    expect(
      await screen.findByRole("heading", { name: "Opciones", level: 1 }),
    ).toBeInTheDocument();
    const seccion = screen.getByRole("region", { name: "Cambiar contraseña" });
    await user.type(
      within(seccion).getByLabelText("Contraseña actual"),
      "Una-clave-actual",
    );
    await user.type(
      within(seccion).getByLabelText("Contraseña nueva"),
      "Una-clave-nueva-2026",
    );
    await user.type(
      within(seccion).getByLabelText("Repetir contraseña nueva"),
      "Una-clave-nueva-2026",
    );
    await user.click(
      within(seccion).getByRole("button", { name: "Guardar contraseña" }),
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Contraseña actualizada.",
    );
    expect(
      screen.getByRole("heading", { name: "Opciones", level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Contraseña actual")).toHaveValue("");
    expect(queryClient.getQueryData<Session>(sessionQueryKey)?.csrf_token).toBe(
      "csrf-renovado",
    );
    expect(csrfHeader).toBe("csrf-firmado");
    expect(requestCredentials).toBe("include");
    await user.click(screen.getByRole("link", { name: "Volver al inicio" }));
    expect(
      await screen.findByRole("heading", { name: "Bienvenido a RescueSync" }),
    ).toBeInTheDocument();
  });

  it("redirige la antigua vista de contraseña a la sección de Opciones", async () => {
    server.use(
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json(session)),
    );
    renderApp("/cambiar-password");
    expect(
      await screen.findByRole("heading", { name: "Opciones", level: 1 }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Cambiar contraseña" }),
    ).toBeInTheDocument();
  });

  it("bloquea el acceso al inicio con contraseña temporal y permite cerrar sesión desde Opciones", async () => {
    server.use(
      http.get(`${API_URL}/auth/me`, () =>
        HttpResponse.json(sessionForRole("OPERADOR_MUNICIPAL", true)),
      ),
      http.post(
        `${API_URL}/auth/logout`,
        () => new HttpResponse(null, { status: 204 }),
      ),
    );
    const user = userEvent.setup();
    renderApp("/");
    expect(
      await screen.findByRole("heading", { name: "Opciones", level: 1 }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/La clave asignada es temporal/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Opciones" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Notificaciones" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Cancelar" }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cerrar sesión" }));
    expect(
      await screen.findByRole("heading", { name: "Iniciá sesión" }),
    ).toBeInTheDocument();
  });

  it("muestra los errores de cambio de contraseña y permite cancelar los datos ingresados", async () => {
    server.use(
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json(session)),
      http.post(`${API_URL}/auth/password`, () =>
        HttpResponse.json(
          { detail: "La contraseña actual es incorrecta." },
          { status: 400 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderApp("/opciones");
    await screen.findByRole("heading", { name: "Opciones", level: 1 });
    await user.type(
      screen.getByLabelText("Contraseña actual"),
      "Una-clave-incorrecta",
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
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La contraseña actual es incorrecta.",
    );
    await user.click(
      screen.getByRole("button", { name: "Mostrar: Contraseña actual" }),
    );
    expect(screen.getByLabelText("Contraseña actual")).toHaveAttribute(
      "type",
      "text",
    );
    expect(screen.getByLabelText("Contraseña nueva")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Repetir contraseña nueva")).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Mostrar: Contraseña nueva" }));
    expect(screen.getByLabelText("Contraseña nueva")).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Mostrar: Repetir contraseña nueva" }));
    expect(screen.getByLabelText("Repetir contraseña nueva")).toHaveAttribute("type", "text");
    await user.click(screen.getByRole("button", { name: "Ocultar: Contraseña actual" }));
    expect(screen.getByLabelText("Contraseña actual")).toHaveAttribute("type", "password");
    await user.click(screen.getByRole("button", { name: "Mostrar: Contraseña actual" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.getByLabelText("Contraseña actual")).toHaveValue("");
    expect(screen.getByLabelText("Contraseña nueva")).toHaveValue("");
    expect(screen.getByLabelText("Contraseña nueva")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Repetir contraseña nueva")).toHaveValue("");
    expect(screen.getByLabelText("Contraseña actual")).toHaveAttribute(
      "type",
      "password",
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("permite al administrador crear una cuenta y enviar su clave por correo", async () => {
    const adminSession = sessionForRole("ADMINISTRADOR");
    let createdPayload: unknown;
    server.use(
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json(adminSession)),
      http.get(`${API_URL}/usuarios`, () => HttpResponse.json([])),
      http.get(`${API_URL}/organizaciones`, () =>
        HttpResponse.json([
          {
            id: 3,
            nombre: "Municipio del Delta",
            tipo: "MUNICIPIO",
            activa: true,
          },
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
    expect(
      screen.getByText(/generará una contraseña temporal/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Contraseña temporal"),
    ).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Rol"), "OPERADOR_MUNICIPAL");
    await user.selectOptions(screen.getByLabelText("Organización"), "3");
    await user.click(screen.getByRole("button", { name: "Crear usuario" }));

    expect(await screen.findByText(
      "Usuario creado. La contraseña temporal fue enviada por correo.",
    )).toBeInTheDocument();
    expect(createdPayload).toEqual({
      email: "nuevo@rescuesync.org",
      rol: "OPERADOR_MUNICIPAL",
      organizacion_id: 3,
    });
  });

  it("reintenta el alta nacional pendiente sin volver a crear la organización", async () => {
    let vinculada = false;
    const nationalId = "12345678-1234-4234-8234-123456789abc";
    const organization = {
      id: 90, nombre: "ONG pendiente", tipo: "ONG", activa: true,
    };
    server.use(
      http.get(`${API_URL}/auth/me`, () =>
        HttpResponse.json(sessionForRole("ADMINISTRADOR")),
      ),
      http.get(`${API_URL}/organizaciones`, () =>
        HttpResponse.json([{
          ...organization, ong_nacional_id: vinculada ? nationalId : null,
        }]),
      ),
      http.post(
        `${API_URL}/organizaciones/90/aprovisionamiento-nacional`,
        ({ request }) => {
          expect(request.headers.get("X-CSRF-Token")).toBe("csrf-firmado");
          vinculada = true;
          return HttpResponse.json({ ...organization, ong_nacional_id: nationalId });
        },
      ),
    );
    renderApp("/organizaciones");
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", {
      name: "Reintentar alta nacional",
    }));
    expect(await screen.findByText("Acceso nacional disponible.")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", {
      name: "Reintentar alta nacional",
    })).not.toBeInTheDocument());
  });

  it("permite crear, editar, desactivar y recuperar organizaciones", async () => {
    const adminSession = sessionForRole("ADMINISTRADOR");
    let organizations: Array<{
      id: number;
      nombre: string;
      tipo: "MUNICIPIO" | "CENTRO_COORDINADOR" | "ONG";
      activa: boolean;
    }> = [
      {
        id: 8,
        nombre: "Rescate Inicial",
        tipo: "ONG" as const,
        activa: true,
      },
    ];
    let csrfHeader: string | null = null;
    server.use(
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json(adminSession)),
      http.get(`${API_URL}/organizaciones`, () =>
        HttpResponse.json(organizations),
      ),
      http.post(`${API_URL}/organizaciones`, async ({ request }) => {
        csrfHeader = request.headers.get("X-CSRF-Token");
        expect(await request.json()).toEqual({
          nombre: "Nueva ONG",
          tipo: "ONG",
          email_contacto: null,
        });
        const created = {
          ong_nacional_id: "12345678-1234-4234-8234-123456789abc",
          id: 9,
          nombre: "Nueva ONG",
          tipo: "ONG" as const,
          activa: true,
        };
        organizations = [...organizations, created];
        return HttpResponse.json(created, { status: 201 });
      }),
      http.patch(
        `${API_URL}/organizaciones/:id`,
        async ({ params, request }) => {
          csrfHeader = request.headers.get("X-CSRF-Token");
          const values = (await request.json()) as {
            nombre?: string;
            tipo?: "MUNICIPIO" | "CENTRO_COORDINADOR" | "ONG";
            activa?: boolean;
          };
          const id = Number(params.id);
          const current = organizations.find(
            (organization) => organization.id === id,
          );
          if (!current) return new HttpResponse(null, { status: 404 });
          const updated = { ...current, ...values };
          organizations = organizations.map((organization) =>
            organization.id === id ? updated : organization,
          );
          return HttpResponse.json(updated);
        },
      ),
      http.delete(`${API_URL}/organizaciones/:id`, ({ params, request }) => {
        csrfHeader = request.headers.get("X-CSRF-Token");
        const id = Number(params.id);
        organizations = organizations.map((organization) =>
          organization.id === id
            ? { ...organization, activa: false }
            : organization,
        );
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    renderApp("/organizaciones");

    expect(
      await screen.findByRole("heading", {
        name: "Administración de organizaciones",
      }),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Nombre"), "Nueva ONG");
    await user.selectOptions(screen.getByLabelText("Tipo"), "ONG");
    await user.click(
      screen.getByRole("button", { name: "Crear organización" }),
    );

    expect(await screen.findByText("ONG creada con acceso nacional disponible.")).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Nueva ONG" }),
    ).toBeInTheDocument();
    expect(csrfHeader).toBe("csrf-firmado");

    const createdCard = screen
      .getByRole("heading", { name: "Nueva ONG" })
      .closest("article");
    expect(createdCard).not.toBeNull();
    await user.click(
      within(createdCard!).getByRole("button", { name: "Editar" }),
    );
    const dialog = screen.getByRole("dialog", { name: "Editar Nueva ONG" });
    await user.clear(within(dialog).getByLabelText("Nombre"));
    await user.type(within(dialog).getByLabelText("Nombre"), "ONG Actualizada");
    await user.click(
      within(dialog).getByRole("button", { name: "Guardar cambios" }),
    );

    expect(
      await screen.findByText("Organización actualizada."),
    ).toBeInTheDocument();
    const updatedCard = (await screen.findByRole("heading", {
      name: "ONG Actualizada",
    })).closest("article");
    expect(updatedCard).not.toBeNull();
    await user.click(
      within(updatedCard!).getByRole("button", { name: "Eliminar" }),
    );

    expect(confirm).toHaveBeenCalledWith(
      "¿Eliminar ONG Actualizada? La baja será lógica y también se desactivarán todos sus usuarios.",
    );
    expect(
      await screen.findByText(
        "Organización eliminada de forma lógica y usuarios relacionados desactivados.",
      ),
    ).toBeInTheDocument();
    const inactiveCard = screen
      .getByRole("heading", { name: "ONG Actualizada" })
      .closest("article");
    expect(inactiveCard).not.toBeNull();
    await user.click(
      within(inactiveCard!).getByRole("button", { name: "Recuperar" }),
    );

    expect(
      await screen.findByText(
        "Organización recuperada. Sus usuarios permanecen inactivos.",
      ),
    ).toBeInTheDocument();
    expect(csrfHeader).toBe("csrf-firmado");
    confirm.mockRestore();
  });

  it("reactiva un usuario sin sobrescribir sus datos con valores de la caché", async () => {
    const adminSession = sessionForRole("ADMINISTRADOR");
    const inactiveUser = {
      id: 20,
      email: "operador@rescuesync.org",
      rol: "OPERADOR_MUNICIPAL",
      organizacion: {
        id: 3,
        nombre: "Municipio del Delta",
        tipo: "MUNICIPIO",
        activa: true,
      },
      activo: false,
      requiere_cambio_password: false,
      creado_en: "2026-09-17T20:00:00Z",
      actualizado_en: "2026-09-17T20:00:00Z",
    };
    let updatePayload: unknown;
    server.use(
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json(adminSession)),
      http.get(`${API_URL}/usuarios`, () => HttpResponse.json([inactiveUser])),
      http.get(`${API_URL}/organizaciones`, () =>
        HttpResponse.json([inactiveUser.organizacion]),
      ),
      http.patch(`${API_URL}/usuarios/20`, async ({ request }) => {
        updatePayload = await request.json();
        return HttpResponse.json({ ...inactiveUser, activo: true });
      }),
    );
    const user = userEvent.setup();
    renderApp("/usuarios");

    await user.click(await screen.findByRole("button", { name: "Reactivar" }));

    expect(await screen.findByText("Usuario reactivado.")).toBeInTheDocument();
    expect(updatePayload).toEqual({ activo: true });
  });

  it("no reutiliza el caché de emergencias del usuario anterior tras cerrar e iniciar sesión con otro", async () => {
    const emergenciaDelMunicipio = {
      id: 31,
      municipio_id: 3,
      centro_coordinador_id: null,
      creada_por_usuario_id: 7,
      gravedad: "ALTA",
      zona: "Ribera norte",
      descripcion: "Inundación con familias evacuadas",
      estado: "REGISTRADA",
      tiene_lotes: false,
      bonita_sync: "PENDIENTE",
      bonita_process_instance_id: null,
      creada_en: "2026-09-19T18:20:39.102766Z",
      actualizada_en: "2026-09-19T18:20:39.102766Z",
    };
    const coordinadorSession = sessionForRole("COORDINADOR_REGIONAL");
    let usuarioActivo: "municipio" | "coordinador" = "municipio";
    server.use(
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json(session)),
      http.post(
        `${API_URL}/auth/logout`,
        () => new HttpResponse(null, { status: 204 }),
      ),
      http.post(`${API_URL}/auth/login`, () => {
        usuarioActivo = "coordinador";
        return HttpResponse.json(coordinadorSession);
      }),
      http.get(`${API_URL}/emergencias`, () =>
        usuarioActivo === "municipio"
          ? HttpResponse.json([emergenciaDelMunicipio], { status: 200 })
          : HttpResponse.json([], { status: 200 }),
      ),
    );
    const user = userEvent.setup();
    renderApp("/");

    await user.click(
      await screen.findByRole("link", { name: "Ver mis emergencias" }),
    );
    await screen.findByText("Alta · Ribera norte");

    await user.click(screen.getByRole("link", { name: "Volver al inicio" }));
    await user.click(
      await screen.findByRole("button", { name: "Cerrar sesión" }),
    );
    await screen.findByRole("heading", { name: "Iniciá sesión" });

    await user.type(
      screen.getByRole("textbox", { name: "Correo electrónico" }),
      "coordinador_regional@rescuesync.org",
    );
    await user.type(screen.getByLabelText("Contraseña"), "Una-clave-segura");
    await user.click(
      screen.getByRole("button", { name: "Ingresar a RescueSync" }),
    );

    await user.click(await screen.findByRole("link", { name: "Ver emergencias pendientes" }));
    expect(
      await screen.findByText("No hay emergencias pendientes sin lotes."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Alta · Ribera norte")).not.toBeInTheDocument();
  });

  it("no reutiliza el caché de emergencias tras expirar la sesión (sin logout explícito) e iniciar sesión con otro usuario", async () => {
    const emergenciaDelMunicipio = {
      id: 31,
      municipio_id: 3,
      centro_coordinador_id: null,
      creada_por_usuario_id: 7,
      gravedad: "ALTA",
      zona: "Ribera norte",
      descripcion: "Inundación con familias evacuadas",
      estado: "REGISTRADA",
      tiene_lotes: false,
      bonita_sync: "PENDIENTE",
      bonita_process_instance_id: null,
      creada_en: "2026-09-19T18:20:39.102766Z",
      actualizada_en: "2026-09-19T18:20:39.102766Z",
    };
    const coordinadorSession = sessionForRole("COORDINADOR_REGIONAL");
    let sesionVigente: "municipio" | "vencida" | "coordinador" = "municipio";
    server.use(
      http.get(`${API_URL}/auth/me`, () =>
        sesionVigente === "municipio"
          ? HttpResponse.json(session)
          : HttpResponse.json(
              { detail: "La sesión no es válida o expiró." },
              { status: 401 },
            ),
      ),
      http.post(`${API_URL}/auth/login`, () => {
        sesionVigente = "coordinador";
        return HttpResponse.json(coordinadorSession);
      }),
      http.get(`${API_URL}/emergencias`, () =>
        sesionVigente === "municipio"
          ? HttpResponse.json([emergenciaDelMunicipio], { status: 200 })
          : HttpResponse.json([], { status: 200 }),
      ),
    );
    const user = userEvent.setup();
    const queryClient = renderApp("/");

    await user.click(
      await screen.findByRole("link", { name: "Ver mis emergencias" }),
    );
    await screen.findByText("Alta · Ribera norte");

    // Simula que la sesión venció del lado del servidor (sin que nadie use
    // el botón "Cerrar sesión") forzando un refetch de /auth/me, que ahora
    // responde 401.
    sesionVigente = "vencida";
    await queryClient.invalidateQueries({ queryKey: sessionQueryKey });
    await screen.findByRole("heading", { name: "Iniciá sesión" });

    await user.type(
      screen.getByRole("textbox", { name: "Correo electrónico" }),
      "coordinador_regional@rescuesync.org",
    );
    await user.type(screen.getByLabelText("Contraseña"), "Una-clave-segura");
    await user.click(
      screen.getByRole("button", { name: "Ingresar a RescueSync" }),
    );

    await user.click(await screen.findByRole("link", { name: "Ver emergencias pendientes" }));
    expect(
      await screen.findByText("No hay emergencias pendientes sin lotes."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Alta · Ribera norte")).not.toBeInTheDocument();
  });
});

describe("emergencias del municipio", () => {
  it("navega entre las tarjetas y las vistas, y actualiza el listado después del alta", async () => {
    let emergencias: unknown[] = [];
    const emergencia = {
      id: 31,
      municipio_id: 3,
      centro_coordinador_id: null,
      creada_por_usuario_id: 7,
      gravedad: "ALTA",
      zona: "Ribera norte",
      descripcion: "Inundación con familias evacuadas",
      estado: "REGISTRADA",
      tiene_lotes: false,
      bonita_sync: "PENDIENTE",
      bonita_process_instance_id: null,
      creada_en: "2026-09-19T18:20:39.102766Z",
      actualizada_en: "2026-09-19T18:20:39.102766Z",
    };
    server.use(
      http.get(`${API_URL}/auth/me`, () => HttpResponse.json(session)),
      http.get(`${API_URL}/emergencias`, () => HttpResponse.json(emergencias)),
      http.post(`${API_URL}/emergencias`, async ({ request }) => {
        expect(request.headers.get("X-CSRF-Token")).toBe(session.csrf_token);
        expect(await request.json()).toEqual({
          gravedad: "ALTA",
          zona: "Ribera norte",
          descripcion: "Inundación con familias evacuadas",
        });
        emergencias = [emergencia];
        return HttpResponse.json(emergencia, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderApp("/");

    await user.click(
      await screen.findByRole("link", { name: "Ver mis emergencias" }),
    );
    expect(
      await screen.findByText("Todavía no registraste emergencias."),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Zona afectada")).not.toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Volver al inicio" }));
    await user.click(screen.getByRole("link", { name: "Registrar emergencia" }));
    expect(
      screen.getByRole("heading", { level: 1, name: "Nueva emergencia" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Mis emergencias" }),
    ).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Gravedad"), "ALTA");
    await user.type(screen.getByLabelText("Zona afectada"), "Ribera norte");
    await user.type(
      screen.getByLabelText("Descripción inicial"),
      "Inundación con familias evacuadas",
    );
    await user.click(screen.getByRole("button", { name: "Registrar emergencia" }));
    expect(
      await screen.findByText("Emergencia 31 registrada en estado REGISTRADA."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Ver mis emergencias" }));
    expect(await screen.findByText("Alta · Ribera norte")).toBeInTheDocument();
    expect(
      screen.queryByText("Todavía no registraste emergencias."),
    ).not.toBeInTheDocument();
    await user.click(screen.getByText("Alta · Ribera norte"));
    expect(
      screen.getByRole("button", { name: "Vincular con Bonita" }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Registrar emergencia" }));
    expect(screen.getByLabelText("Zona afectada")).toHaveValue("");
    await user.click(screen.getByRole("link", { name: "Volver al inicio" }));
    expect(
      screen.getByRole("heading", { name: "Bienvenido a RescueSync" }),
    ).toBeInTheDocument();
  });

  it.each(["/emergencias/nueva", "/mis-emergencias"])(
    "permite al municipio abrir directamente %s",
    async (path) => {
      server.use(http.get(`${API_URL}/auth/me`, () => HttpResponse.json(session)));
      renderApp(path);
      expect(
        await screen.findByRole("heading", {
          level: 1,
          name: path === "/emergencias/nueva"
            ? "Nueva emergencia"
            : "Emergencias de mi municipio",
        }),
      ).toBeInTheDocument();
    },
  );

  it.each([
    "/emergencias/nueva", "/mis-emergencias",
    "/mis-recursos/certificaciones", "/mis-recursos/inventario",
    "/emergencias/pendientes", "/emergencias/con-lotes",
  ])(
    "redirige al login si se abre %s sin sesión",
    async (path) => {
      server.use(
        http.get(`${API_URL}/auth/me`, () =>
          HttpResponse.json(
            { detail: "La sesión no es válida o expiró." },
            { status: 401 },
          ),
        ),
      );
      renderApp(path);
      expect(
        await screen.findByRole("heading", { name: "Iniciá sesión" }),
      ).toBeInTheDocument();
    },
  );

  describe.each(["/emergencias/nueva", "/mis-emergencias"])("acceso a %s", (path) => {
    it.each<Role>([
      "ADMINISTRADOR",
      "COORDINADOR_REGIONAL",
      "REPRESENTANTE_ONG",
      "AUDITOR_DIRECTIVO",
    ])("impide a %s abrir una vista municipal", async (role) => {
      server.use(
        http.get(`${API_URL}/auth/me`, () => HttpResponse.json(sessionForRole(role))),
      );
      renderApp(path);

      expect(
        await screen.findByRole("heading", { name: role === "AUDITOR_DIRECTIVO" ? "Dashboard de auditoría" : "Bienvenido a RescueSync" }),
      ).toBeInTheDocument();
      expect(screen.queryByLabelText("Zona afectada")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("heading", { name: "Emergencias de mi municipio" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("link", { name: "Ver mis emergencias" }),
      ).not.toBeInTheDocument();
    });
  });
});

describe("navegación por rol", () => {
  describe.each([
    ["/mis-recursos/certificaciones", "Certificaciones de mi ONG"],
    ["/mis-recursos/inventario", "Inventario de mi ONG"],
  ])("acceso directo a %s", (path, heading) => {
    it("permite abrir la vista al representante de ONG", async () => {
      server.use(
        http.get(`${API_URL}/auth/me`, () =>
          HttpResponse.json(sessionForRole("REPRESENTANTE_ONG")),
        ),
        http.get(`${API_URL}/mi-ong/conexion`, () => HttpResponse.json({
          estado: "SIN_CONFIGURAR", vinculada: true, conectada: false,
          ongId: "00000000-0000-4000-8000-000000000001", expiraEn: null,
        })),
      );
      renderApp(path);
      expect(await screen.findByRole("heading", { name: heading, level: 1 })).toBeInTheDocument();
    });

    it.each<Role>([
      "ADMINISTRADOR", "COORDINADOR_REGIONAL", "OPERADOR_MUNICIPAL", "AUDITOR_DIRECTIVO",
    ])("impide que %s abra la vista de una ONG", async (role) => {
      server.use(
        http.get(`${API_URL}/auth/me`, () => HttpResponse.json(sessionForRole(role))),
        http.get(`${API_URL}/emergencias`, () => HttpResponse.json([])),
      );
      renderApp(path);
      expect(await screen.findByRole("heading", { name: /Bienvenido a RescueSync|Dashboard de auditoría/ })).toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: heading, level: 1 })).not.toBeInTheDocument();
    });
  });

  it.each<Role>(["OPERADOR_MUNICIPAL", "COORDINADOR_REGIONAL", "REPRESENTANTE_ONG", "AUDITOR_DIRECTIVO"])(
    "impide a %s abrir la administración del catálogo nacional",
    async (role) => {
      server.use(
        http.get(`${API_URL}/auth/me`, () => HttpResponse.json(sessionForRole(role))),
        http.get(`${API_URL}/emergencias`, () => HttpResponse.json([])),
      );
      renderApp("/catalogo-nacional");
      expect(await screen.findByRole("heading", { name: /Bienvenido a RescueSync|Dashboard de auditoría/ })).toBeInTheDocument();
      expect(screen.queryByRole("heading", { name: "Crear capacidad" })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: "Gestionar capacidades" })).not.toBeInTheDocument();
    },
  );

  it.each<{
    role: Role;
    visible: string | null;
    hidden: string[];
  }>([
    {
      role: "OPERADOR_MUNICIPAL",
      visible: "Registrar emergencia",
      hidden: ["Emergencias pendientes", "Presentar oferta"],
    },
    {
      role: "COORDINADOR_REGIONAL",
      visible: "Emergencias pendientes",
      hidden: ["Registrar emergencia", "Presentar oferta"],
    },
    {
      role: "REPRESENTANTE_ONG",
      visible: "Presentar oferta",
      hidden: ["Registrar emergencia", "Mis emergencias", "Emergencias pendientes"],
    },
    {
      role: "AUDITOR_DIRECTIVO",
      visible: null,
      hidden: ["Registrar emergencia", "Emergencias pendientes", "Presentar oferta"],
    },
    {
      role: "ADMINISTRADOR",
      visible: "Gestionar usuarios",
      hidden: ["Registrar emergencia", "Emergencias pendientes", "Presentar oferta"],
    },
  ])("muestra únicamente las acciones habilitadas para $role", async (testCase) => {
    server.use(
      http.get(`${API_URL}/auth/me`, () =>
        HttpResponse.json(sessionForRole(testCase.role)),
      ),
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json([], { status: 200 }),
      ),
    );
    renderApp("/");

    expect(
      await screen.findByRole("heading", { name: /Bienvenido a RescueSync|Dashboard de auditoría/ }),
    ).toBeInTheDocument();

    if (testCase.visible === null) {
      expect(
        await screen.findByRole("heading", { name: "Panel de indicadores" }),
      ).toBeInTheDocument();
    } else {
      expect(
        await screen.findByRole("heading", { name: testCase.visible }),
      ).toBeInTheDocument();
    }

    for (const hiddenAction of testCase.hidden) {
      expect(
        screen.queryByRole("heading", { name: hiddenAction }),
      ).not.toBeInTheDocument();
    }
  });
});


describe.each(["/emergencias/pendientes", "/emergencias/con-lotes"])("acceso a la bandeja del coordinador %s", (path) => {
  it.each<Role>(["OPERADOR_MUNICIPAL", "REPRESENTANTE_ONG", "AUDITOR_DIRECTIVO", "ADMINISTRADOR"])(
    "impide el acceso a %s",
    async (role) => {
      server.use(http.get(`${API_URL}/auth/me`, () => HttpResponse.json(sessionForRole(role))));
      renderApp(path);
      expect(await screen.findByRole("heading", { name: /Bienvenido a RescueSync|Dashboard de auditoría/ })).toBeInTheDocument();
      expect(screen.queryByRole("heading", { level: 1, name: /Emergencias pendientes|Emergencias no pendientes/ })).not.toBeInTheDocument();
    },
  );
});
