import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router";
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
} from "vitest";
import type { Session } from "../schemas/auth";
import { MisRecursosPage } from "./MisRecursosPage";

const base = "http://localhost:8000/api/v1/mi-ong";
const ong = "00000000-0000-4000-8000-000000000001";
const capacidadId = "00000000-0000-4000-8000-000000000002";
const recurso = {
  id: "00000000-0000-4000-8000-000000000003",
  ongId: ong,
  capacidadId,
  codigoInterno: "AMB-01",
  nombre: "Ambulancias de rescate",
  capacidad: "Ambulancias",
  unidad: "vehículos",
  admiteFracciones: false,
  cantidadTotal: "10.000",
  cantidadComprometida: "4.000",
  cantidadDisponible: "6.000",
  activo: true,
  actualizadoEn: "2026-10-08T12:00:00Z",
};
const session: Session = {
  usuario: {
    id: 7,
    email: "ong@rescuesync.org",
    rol: "REPRESENTANTE_ONG",
    organizacion: { id: 4, nombre: "ONG de prueba", tipo: "ONG" },
    requiere_cambio_password: false,
  },
  csrf_token: "csrf-demo",
};
const server = setupServer();
let conectada = true;
let recursos = [recurso];

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  conectada = true;
  recursos = [recurso];
  server.use(
    http.get(`${base}/conexion`, () =>
      HttpResponse.json({
        vinculada: true,
        conectada,
        ongId: ong,
        expiraEn: conectada ? "2026-10-08T13:00:00Z" : null,
      }),
    ),
    http.get(`${base}/recursos`, () => HttpResponse.json(recursos)),
    http.get(`${base}/capacidades`, () =>
      HttpResponse.json([
        {
          id: capacidadId,
          codigo: "AMBULANCIAS",
          nombre: "Ambulancias",
          tipo: "VEHICULO",
          unidad: "vehículos",
          admiteFracciones: false,
        },
      ]),
    ),
  );
});
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
function renderPage(): void {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MisRecursosPage session={session} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Mis recursos nacionales", () => {
  it("presenta la vinculación pendiente sin pedir credenciales", async () => {
    server.use(
      http.get(`${base}/conexion`, () =>
        HttpResponse.json({
          vinculada: false,
          conectada: false,
          ongId: null,
          expiraEn: null,
        }),
      ),
    );
    renderPage();
    expect(
      await screen.findByRole("heading", { name: "Vinculación pendiente" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Contraseña nacional"),
    ).not.toBeInTheDocument();
  });
  it("conecta la cuenta nacional usando CSRF y consulta el inventario", async () => {
    conectada = false;
    server.use(
      http.post(`${base}/conexion`, async ({ request }) => {
        expect(request.headers.get("X-CSRF-Token")).toBe("csrf-demo");
        expect(await request.json()).toEqual({
          identificadorLogin: "ong@nacional.org",
          password: "clave-nacional",
        });
        conectada = true;
        return HttpResponse.json({
          vinculada: true,
          conectada: true,
          ongId: ong,
          expiraEn: "2026-10-08T13:00:00Z",
        });
      }),
    );
    renderPage();
    const user = userEvent.setup();
    await user.type(
      await screen.findByLabelText("Identificador nacional"),
      "ong@nacional.org",
    );
    await user.type(
      screen.getByLabelText("Contraseña nacional"),
      "clave-nacional",
    );
    await user.click(screen.getByRole("button", { name: "Conectar cuenta" }));
    expect(
      await screen.findByRole("heading", { name: "Ambulancias de rescate" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByLabelText("Contraseña nacional"),
    ).not.toBeInTheDocument();
  });
  it("registra recursos y rechaza fracciones para vehículos", async () => {
    recursos = [];
    let llamadas = 0;
    server.use(
      http.post(`${base}/recursos`, async ({ request }) => {
        llamadas++;
        const body = await request.json();
        expect(body).toEqual({
          capacidadId,
          codigoInterno: "AMB-01",
          nombre: "Ambulancias",
          cantidadTotal: "3",
        });
        recursos = [recurso];
        return HttpResponse.json(recurso, { status: 201 });
      }),
    );
    renderPage();
    const user = userEvent.setup();
    await user.selectOptions(
      await screen.findByLabelText("Capacidad y unidad"),
      capacidadId,
    );
    await user.type(screen.getByLabelText("Código interno"), "AMB-01");
    await user.type(screen.getByLabelText("Nombre del recurso"), "Ambulancias");
    await user.type(screen.getByLabelText(/Cantidad total/), "0");
    await user.click(screen.getByRole("button", { name: "Registrar recurso" }));
    expect(await screen.findByText("La cantidad debe ser mayor que cero.")).toBeInTheDocument();
    expect(llamadas).toBe(0);
    await user.clear(screen.getByLabelText(/Cantidad total/));
    await user.type(screen.getByLabelText(/Cantidad total/), "2.5");
    await user.click(screen.getByRole("button", { name: "Registrar recurso" }));
    expect(
      await screen.findByText("Esta capacidad requiere cantidades enteras."),
    ).toBeInTheDocument();
    expect(llamadas).toBe(0);
    await user.clear(screen.getByLabelText(/Cantidad total/));
    await user.type(screen.getByLabelText(/Cantidad total/), "3");
    await user.click(screen.getByRole("button", { name: "Registrar recurso" }));
    expect(await screen.findByText("Recurso registrado.")).toBeInTheDocument();
  });
  it("no reduce el total por debajo del comprometido y envía la versión al editar", async () => {
    let llamadas = 0;
    server.use(
      http.patch(`${base}/recursos/${recurso.id}`, async ({ request }) => {
        llamadas++;
        expect(await request.json()).toEqual({
          cantidadTotal: "12",
          actualizadoEn: recurso.actualizadoEn,
        });
        recursos = [
          { ...recurso, cantidadTotal: "12.000", cantidadDisponible: "8.000" },
        ];
        return HttpResponse.json(recursos[0]);
      }),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Editar AMB-01" }),
    );
    await user.clear(screen.getByLabelText(/Nuevo total/));
    await user.type(screen.getByLabelText(/Nuevo total/), "3");
    await user.click(screen.getByRole("button", { name: "Guardar cantidad" }));
    expect(
      await screen.findByText(/El total debe ser al menos 4.000/),
    ).toBeInTheDocument();
    expect(llamadas).toBe(0);
    await user.clear(screen.getByLabelText(/Nuevo total/));
    await user.type(screen.getByLabelText(/Nuevo total/), "12");
    await user.click(screen.getByRole("button", { name: "Guardar cantidad" }));
    expect(
      await screen.findByText("Cantidad actualizada."),
    ).toBeInTheDocument();
    expect(await screen.findByText("12.000")).toBeInTheDocument();
  });
  it("permite reconectar si el token nacional expiró durante una consulta", async () => {
    server.use(
      http.get(`${base}/recursos`, () => {
        conectada = false;
        return HttpResponse.json(
          { detail: "La credencial nacional expiró." },
          { status: 401 },
        );
      }),
    );
    renderPage();
    expect(
      await screen.findByRole("heading", { name: "Conectar cuenta nacional" }),
    ).toBeInTheDocument();
  });
  it("conserva la edición y muestra el conflicto devuelto por el backend", async () => {
    server.use(
      http.patch(`${base}/recursos/${recurso.id}`, () =>
        HttpResponse.json(
          { detail: "El recurso cambió. Actualizá el listado." },
          { status: 409 },
        ),
      ),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(
      await screen.findByRole("button", { name: "Editar AMB-01" }),
    );
    await user.click(screen.getByRole("button", { name: "Guardar cantidad" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("El recurso cambió."),
    );
    expect(screen.getByLabelText(/Nuevo total/)).toBeInTheDocument();
  });

  it("registra una ONG pendiente y muestra el UUID para vinculación administrativa", async () => {
    server.use(
      http.get(`${base}/conexion`, () => HttpResponse.json({ vinculada: false, conectada: false, ongId: null, expiraEn: null })),
      http.post(`${base}/registro-nacional`, async ({ request }) => {
        expect(request.headers.get("X-CSRF-Token")).toBe("csrf-demo");
        expect(await request.json()).toEqual({ identificadorInstitucional: "registro:123", emailContacto: "contacto@example.org", identificadorLogin: "nueva@nacional.org", password: "clave-nacional123" });
        return HttpResponse.json({ id: ong, nombre: "ONG de prueba", estado: "PENDIENTE" }, { status: 201 });
      }),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Registrar ONG en el Sistema Nacional" }));
    await user.type(screen.getByLabelText("Identificador institucional"), "registro:123");
    await user.type(screen.getByLabelText("Email de contacto"), "contacto@example.org");
    await user.type(screen.getByLabelText("Nuevo identificador nacional"), "nueva@nacional.org");
    await user.type(screen.getByLabelText("Nueva contraseña nacional"), "clave-nacional123");
    await user.click(screen.getByRole("button", { name: "Crear registro nacional" }));
    expect(await screen.findByText("ONG registrada en estado pendiente.")).toBeInTheDocument();
    expect(screen.getByText(ong)).toBeInTheDocument();
    expect(screen.queryByLabelText("Nueva contraseña nacional")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Cuenta nacional conectada" })).not.toBeInTheDocument();
  });

  it("presenta un duplicado de registro y borra la contraseña para un nuevo intento", async () => {
    server.use(
      http.get(`${base}/conexion`, () => HttpResponse.json({ vinculada: false, conectada: false, ongId: null, expiraEn: null })),
      http.post(`${base}/registro-nacional`, () => HttpResponse.json({ detail: "La ONG ya está registrada." }, { status: 409 })),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Registrar ONG en el Sistema Nacional" }));
    await user.type(screen.getByLabelText("Identificador institucional"), "registro:123");
    await user.type(screen.getByLabelText("Email de contacto"), "contacto@example.org");
    await user.type(screen.getByLabelText("Nuevo identificador nacional"), "nueva@nacional.org");
    await user.type(screen.getByLabelText("Nueva contraseña nacional"), "clave-nacional123");
    await user.click(screen.getByRole("button", { name: "Crear registro nacional" }));
    expect(await screen.findByText("La ONG ya está registrada.")).toBeInTheDocument();
    expect(screen.getByLabelText("Nueva contraseña nacional")).toHaveValue("");
    expect(screen.getByLabelText("Identificador institucional")).toHaveValue("registro:123");
  });
});
