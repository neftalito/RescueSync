import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router";
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
import { PerfilCompetenciaOngPage, InventarioOngPage } from "./GestionRecursosOngPage";

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
const perfil = {
  ongId: ong, nombre: "ONG de prueba", estadoOng: "HABILITADA",
  evaluadoEn: "2026-10-14T12:00:00Z",
  capacidadesDeclaradas: [{
    capacidadId, codigo: "AMBULANCIAS", nombre: "Ambulancias", tipo: "VEHICULO",
    unidad: "vehículos", admiteFracciones: false,
    cantidadTotal: "10.000", cantidadComprometida: "4.000", cantidadDisponible: "6.000",
  }],
};
const server = setupServer();
let conectada = true;
let recursos = [recurso];

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
  // JSDOM no implementa la apertura y el cierre de diálogos nativos.
  HTMLDialogElement.prototype.showModal = function (): void {
    this.open = true;
  };
  HTMLDialogElement.prototype.close = function (): void {
    this.open = false;
  };
});
beforeEach(() => {
  conectada = true;
  recursos = [recurso];
  server.use(
    http.get(`${base}/perfil-competencia`, () => HttpResponse.json(perfil)),
    http.get(`${base}/conexion`, () =>
      HttpResponse.json({
        vinculada: true,
        conectada,
        estado: conectada ? "LISTA" : "REQUIERE_REVISION",
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
function renderPage(vista: "inicio" | "inventario" | "perfil-competencia" = "inventario"): void {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[vista === "inicio" ? "/mis-recursos" : `/mis-recursos/${vista}`]}>
        <Routes>
          <Route path="/mis-recursos" element={<MisRecursosPage session={session} />} />
          <Route path="/mis-recursos/inventario" element={<InventarioOngPage session={session} />} />
          <Route path="/mis-recursos/perfil-competencia" element={<PerfilCompetenciaOngPage session={session} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Mis recursos nacionales", () => {
  it("busca recursos por nombre o código en el inventario", async () => {
    recursos = [recurso, { ...recurso, id: "00000000-0000-4000-8000-000000000105", codigoInterno: "MED-02", nombre: "Módulo de oxígeno" }];
    renderPage("inventario");
    const user = userEvent.setup();
    await screen.findByRole("heading", { name: "Ambulancias de rescate" });
    const busqueda = screen.getByRole("searchbox", { name: "Buscar recursos" });

    await user.type(busqueda, "OXIGENO");
    expect(screen.getByRole("heading", { name: "Módulo de oxígeno" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Ambulancias de rescate" })).not.toBeInTheDocument();
    await user.clear(busqueda);
    await user.type(busqueda, "amb-01");
    expect(screen.getByRole("heading", { name: "Ambulancias de rescate" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Módulo de oxígeno" })).not.toBeInTheDocument();
  });

  it("ofrece dos tarjetas y navega a vistas independientes sin cargar datos ajenos", async () => {
    let consultasInventario = 0;
    let consultasPerfiles = 0;
    server.use(
      http.get(`${base}/recursos`, () => {
        consultasInventario++;
        return HttpResponse.json(recursos);
      }),
      http.get(`${base}/perfil-competencia`, () => {
        consultasPerfiles++;
        return HttpResponse.json(perfil);
      }),
    );
    renderPage("inicio");
    const user = userEvent.setup();
    const header = screen.getByRole("heading", { name: "Mis recursos", level: 1 }).closest("header");
    expect(within(header!).getByText("RescueSync")).toBeInTheDocument();
    expect(within(header!).getByRole("link", { name: "Volver al inicio" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Ver perfil de competencia" })).toHaveAttribute("href", "/mis-recursos/perfil-competencia");
    expect(screen.getByRole("link", { name: "Gestionar inventario" })).toHaveAttribute("href", "/mis-recursos/inventario");
    expect(consultasInventario).toBe(0);
    expect(consultasPerfiles).toBe(0);
    await user.click(screen.getByRole("link", { name: "Ver perfil de competencia" }));
    expect(await screen.findByText("ONG de prueba · Activa")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Perfil de competencia de mi ONG", level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Registrar recurso" })).not.toBeInTheDocument();
    expect(consultasInventario).toBe(0);
    const consultasPerfil = consultasPerfiles;
    await user.click(screen.getByRole("link", { name: "Volver a Mis recursos" }));
    await user.click(screen.getByRole("link", { name: "Gestionar inventario" }));
    expect(await screen.findByRole("heading", { name: "Ambulancias de rescate" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Inventario de mi ONG", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Registrar recurso" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Perfil de competencia" })).not.toBeInTheDocument();
    expect(consultasPerfiles).toBe(consultasPerfil);
    expect(consultasInventario).toBe(1);
  });

  it("describe recursos sin certificados ni permisos por riesgo", async () => {
    renderPage("perfil-competencia");
    expect(await screen.findByRole("heading", { name: "Ambulancias" })).toBeInTheDocument();
    expect(screen.getByText("10.000 vehículos")).toBeInTheDocument();
    expect(screen.getByText("4.000 vehículos")).toBeInTheDocument();
    expect(screen.getByText("6.000 vehículos")).toBeInTheDocument();
    expect(screen.queryByText(/riesgo permitido/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/acreditaciones/i)).not.toBeInTheDocument();
  });

  it("conserva capacidades cuando el stock está completamente comprometido", async () => {
    server.use(http.get(`${base}/perfil-competencia`, () => HttpResponse.json({
      ...perfil, capacidadesDeclaradas: [{ ...perfil.capacidadesDeclaradas[0], cantidadComprometida: "10.000", cantidadDisponible: "0.000" }],
    })));
    renderPage("perfil-competencia");
    expect(await screen.findByRole("heading", { name: "Ambulancias" })).toBeInTheDocument();
    expect(screen.getByText("0.000 vehículos")).toBeInTheDocument();
  });

  it("muestra un perfil vacío sin exigir validación", async () => {
    server.use(http.get(`${base}/perfil-competencia`, () => HttpResponse.json({ ...perfil, capacidadesDeclaradas: [] })));
    renderPage("perfil-competencia");
    expect(await screen.findByText("No hay recursos activos declarados.")).toBeInTheDocument();
  });

  it("permite reintentar una consulta fallida sin conservar un perfil habilitado", async () => {
    server.use(
      http.get(`${base}/perfil-competencia`, () =>
        HttpResponse.json(
          { detail: "El Sistema Nacional demoró en responder." },
          { status: 504 },
        ),
      ),
    );
    renderPage("perfil-competencia");
    expect(
      await screen.findByText("El Sistema Nacional demoró en responder."),
    ).toBeInTheDocument();
    server.use(
      http.get(`${base}/perfil-competencia`, () => HttpResponse.json(perfil)),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Actualizar perfil" }),
    );
    expect(
      await screen.findByText("ONG de prueba · Activa"),
    ).toBeInTheDocument();
  });
  it("muestra revisión administrativa ante revocación del acceso", async () => {
    server.use(
      http.get(`${base}/perfil-competencia`, () => {
        conectada = false;
        return HttpResponse.json(
          { detail: "La credencial nacional expiró." },
          { status: 401 },
        );
      }),
    );
    renderPage("perfil-competencia");
    expect(
      await screen.findByRole("heading", { name: "El acceso nacional requiere revisión" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Perfil de competencia" }),
    ).not.toBeInTheDocument();
  });
  it("presenta la vinculación pendiente sin pedir credenciales", async () => {
    server.use(
      http.get(`${base}/conexion`, () =>
        HttpResponse.json({
          estado: "SIN_CONFIGURAR",
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
  it("consulta inventario automáticamente aunque todavía no haya token", async () => {
    conectada = false;
    server.use(http.get(`${base}/conexion`, () => HttpResponse.json({
      vinculada: true, conectada: false, estado: "LISTA", ongId: ong, expiraEn: null,
    })));
    renderPage();
    expect(await screen.findByRole("heading", { name: "Ambulancias de rescate" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Contraseña nacional")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Desconectar" })).not.toBeInTheDocument();
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
          codigoInterno: "Ambulancia de guardia",
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
    await user.type(
      screen.getByLabelText("Descripción corta"),
      "Ambulancia de guardia",
    );
    await user.type(screen.getByLabelText("Nombre del recurso"), "Ambulancias");
    await user.type(screen.getByLabelText(/Cantidad total/), "0");
    await user.click(screen.getByRole("button", { name: "Registrar recurso" }));
    expect(
      await screen.findByText("La cantidad debe ser mayor que cero."),
    ).toBeInTheDocument();
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
  it("abre la edición en un modal y descarta los cambios al cancelar", async () => {
    renderPage();
    const user = userEvent.setup();
    const editar = await screen.findByRole("button", { name: "Editar AMB-01" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(editar);
    const dialog = screen.getByRole("dialog", {
      name: "Editar cantidad: Ambulancias de rescate",
    });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    const cantidad = within(dialog).getByLabelText(/Nuevo total/);
    expect(cantidad).toHaveValue("10.000");
    expect(cantidad).toHaveFocus();
    await user.clear(cantidad);
    await user.type(cantidad, "15");
    await user.click(within(dialog).getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(editar);
    expect(screen.getByLabelText(/Nuevo total/)).toHaveValue("10.000");
    await user.click(screen.getByRole("button", { name: "Cerrar edición" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByText("Cantidad actualizada.")).not.toBeInTheDocument();
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
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(await screen.findByText("12.000")).toBeInTheDocument();
  });
  it("muestra revisión administrativa sin pedir contraseña", async () => {
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
      await screen.findByRole("heading", { name: "El acceso nacional requiere revisión" }),
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
    expect(within(screen.getByRole("dialog")).getByLabelText(/Nuevo total/))
      .toBeInTheDocument();
  });

  it("activa el acceso nacional sin pedir identificadores ni contraseñas", async () => {
    let registrada = false;
    server.use(
      http.get(`${base}/conexion`, () =>
        HttpResponse.json({
          estado: registrada ? "LISTA" : "SIN_CONFIGURAR",
          vinculada: registrada,
          conectada: false,
          ongId: registrada ? ong : null,
          expiraEn: null,
        }),
      ),
      http.post(`${base}/registro-nacional`, async ({ request }) => {
        expect(request.headers.get("X-CSRF-Token")).toBe("csrf-demo");
        expect(await request.json()).toEqual({ emailContacto: null });
        registrada = true;
        return HttpResponse.json(
          { id: ong, nombre: "ONG de prueba", estado: "PENDIENTE" },
          { status: 201 },
        );
      }),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Registrar ONG en el Sistema Nacional" }));
    expect(screen.getByLabelText("Email de contacto (opcional)")).toBeInTheDocument();
    expect(screen.queryByLabelText("Identificador institucional")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Nueva contraseña nacional")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Crear registro nacional" }));
    expect(await screen.findByRole("region", { name: "Recursos de mi ONG" })).toBeInTheDocument();
  });

  it("conserva el correo opcional ante un error y permite reintentar", async () => {
    server.use(
      http.get(`${base}/conexion`, () =>
        HttpResponse.json({
          estado: "SIN_CONFIGURAR", vinculada: false,
          conectada: false, ongId: null, expiraEn: null,
        }),
      ),
      http.post(`${base}/registro-nacional`, () =>
        HttpResponse.json({ detail: "La ONG ya está registrada." }, { status: 409 }),
      ),
    );
    renderPage();
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "Registrar ONG en el Sistema Nacional" }));
    await user.type(screen.getByLabelText("Email de contacto (opcional)"), "contacto@example.org");
    await user.click(screen.getByRole("button", { name: "Crear registro nacional" }));
    expect(await screen.findByText("La ONG ya está registrada.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email de contacto (opcional)")).toHaveValue("contacto@example.org");
  });
});
