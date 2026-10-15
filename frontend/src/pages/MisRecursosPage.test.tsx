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
import { CertificacionesOngPage, InventarioOngPage } from "./GestionRecursosOngPage";

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
const certificacion = {
  id: "00000000-0000-4000-8000-000000000010",
  codigo: "SANITARIA",
  revision: 1,
  nombre: "Respuesta sanitaria",
  activa: true,
  alcances: [
    {
      capacidadId,
      codigo: "AMBULANCIAS",
      nombre: "Ambulancias",
      tipo: "VEHICULO",
      unidad: "vehículos",
      admiteFracciones: false,
      activa: true,
      riesgoMaximo: "MEDIA",
    },
  ],
};
const perfil = {
  ongId: ong,
  estadoOng: "HABILITADA",
  evaluadoEn: "2026-10-14T12:00:00Z",
  acreditaciones: [],
  capacidadesHabilitadas: [],
  motivosInstitucionales: [],
};
const server = setupServer();
let conectada = true;
let recursos = [recurso];

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
beforeEach(() => {
  conectada = true;
  recursos = [recurso];
  server.use(
    http.get(`${base}/certificaciones`, () => HttpResponse.json(perfil)),
    http.get(`${base}/catalogo-certificaciones`, () =>
      HttpResponse.json([certificacion]),
    ),
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
function renderPage(vista: "inicio" | "inventario" | "certificaciones" = "inventario"): void {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[vista === "inicio" ? "/mis-recursos" : `/mis-recursos/${vista}`]}>
        <Routes>
          <Route path="/mis-recursos" element={<MisRecursosPage session={session} />} />
          <Route path="/mis-recursos/inventario" element={<InventarioOngPage session={session} />} />
          <Route path="/mis-recursos/certificaciones" element={<CertificacionesOngPage session={session} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Mis recursos nacionales", () => {
  it("ofrece dos tarjetas y navega a vistas independientes sin cargar datos ajenos", async () => {
    let consultasInventario = 0;
    let consultasCertificaciones = 0;
    server.use(
      http.get(`${base}/recursos`, () => {
        consultasInventario++;
        return HttpResponse.json(recursos);
      }),
      http.get(`${base}/certificaciones`, () => {
        consultasCertificaciones++;
        return HttpResponse.json(perfil);
      }),
    );
    renderPage("inicio");
    const user = userEvent.setup();
    const header = screen.getByRole("heading", { name: "Mis recursos", level: 1 }).closest("header");
    expect(within(header!).getByText("RescueSync")).toBeInTheDocument();
    expect(within(header!).getByRole("link", { name: "Volver al inicio" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Ver mis certificaciones" })).toHaveAttribute("href", "/mis-recursos/certificaciones");
    expect(screen.getByRole("link", { name: "Gestionar inventario" })).toHaveAttribute("href", "/mis-recursos/inventario");
    expect(consultasInventario).toBe(0);
    expect(consultasCertificaciones).toBe(0);
    await user.click(screen.getByRole("link", { name: "Ver mis certificaciones" }));
    expect(await screen.findByText("Habilitada")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Certificaciones de mi ONG", level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Registrar recurso" })).not.toBeInTheDocument();
    expect(consultasInventario).toBe(0);
    const consultasPerfil = consultasCertificaciones;
    await user.click(screen.getByRole("link", { name: "Volver a Mis recursos" }));
    await user.click(screen.getByRole("link", { name: "Gestionar inventario" }));
    expect(await screen.findByRole("heading", { name: "Ambulancias de rescate" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Inventario de mi ONG", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Registrar recurso" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Mis certificaciones" })).not.toBeInTheDocument();
    expect(consultasCertificaciones).toBe(consultasPerfil);
    expect(consultasInventario).toBe(1);
  });

  it("separa estado, capacidades, historial y catálogo en secciones identificables", async () => {
    renderPage("certificaciones");
    const estado = await screen.findByRole("region", { name: "Estado institucional" });
    expect(await within(estado).findByText("Habilitada")).toBeInTheDocument();
    const capacidades = screen.getByRole("region", { name: "Capacidades habilitadas" });
    expect(within(capacidades).getByText(/Tu ONG no tiene capacidades habilitadas/)).toBeInTheDocument();
    const historial = screen.getByRole("region", { name: "Historial de acreditaciones" });
    expect(within(historial).getByText("Tu ONG todavía no tiene acreditaciones registradas.")).toBeInTheDocument();
    const catalogo = screen.getByRole("region", { name: "Catálogo nacional de certificaciones" });
    expect(within(catalogo).getByText(/Estar en este catálogo no acredita a tu ONG/)).toBeInTheDocument();
    const certificacionCatalogo = await within(catalogo).findByText("Respuesta sanitaria");
    const detalle = certificacionCatalogo.closest("details");
    expect(detalle).not.toHaveAttribute("open");
    await userEvent.click(certificacionCatalogo);
    expect(detalle).toHaveAttribute("open");
    expect(within(catalogo).getByRole("list", {
      name: "Listado de certificaciones nacionales",
    })).toHaveAttribute("tabindex", "0");
    expect(within(catalogo).getByText("Riesgo máximo: Medio")).toBeVisible();
    expect(within(historial).queryByText("Respuesta sanitaria")).not.toBeInTheDocument();
  });

  it("conserva el estado institucional cuando falla únicamente el catálogo", async () => {
    server.use(http.get(`${base}/catalogo-certificaciones`, () =>
      HttpResponse.json({ detail: "No pudimos cargar el catálogo nacional." }, { status: 504 }),
    ));
    renderPage("certificaciones");
    const catalogo = await screen.findByRole("region", { name: "Catálogo nacional de certificaciones" });
    expect(await within(catalogo).findByRole("alert")).toHaveTextContent("No pudimos cargar el catálogo nacional.");
    expect(await within(screen.getByRole("region", {
      name: "Estado institucional",
    })).findByText("Habilitada")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Capacidades habilitadas" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Historial de acreditaciones" })).toBeInTheDocument();
  });

  it("muestra vigencia, vencimiento y niveles de competencia por capacidad", async () => {
    const credencial = {
      id: "00000000-0000-4000-8000-000000000011",
      certificacion,
      emisor: "Autoridad demo",
      numeroCredencial: "DEMO-VIGENTE",
      vigenteDesde: "2026-01-01T00:00:00Z",
      vigenteHasta: "2027-01-01T00:00:00Z",
      estado: "OTORGADA",
      estadoVigencia: "VIGENTE",
      revocadaEn: null,
      motivoRevocacion: null,
      motivos: [],
    };
    server.use(
      http.get(`${base}/certificaciones`, () =>
        HttpResponse.json({
          ...perfil,
          acreditaciones: [
            credencial,
            {
              ...credencial,
              id: "00000000-0000-4000-8000-000000000012",
              numeroCredencial: "DEMO-VENCIDA",
              estadoVigencia: "VENCIDA",
              vigenteHasta: "2026-10-01T00:00:00Z",
              motivos: [
                {
                  codigo: "ACREDITACION_VENCIDA",
                  mensaje: "La acreditación venció.",
                  capacidadId: null,
                },
              ],
            },
          ],
          capacidadesHabilitadas: [
            {
              capacidadId,
              codigo: "AMBULANCIAS",
              nombre: "Ambulancias",
              unidad: "vehículos",
              riesgoMaximo: "MEDIA",
              nivelesRiesgoPermitidos: ["BAJA", "MEDIA"],
              acreditacionIds: [credencial.id],
            },
          ],
        }),
      ),
    );
    renderPage("certificaciones");
    expect(
      await screen.findByText("DEMO-VIGENTE"),
    ).toBeInTheDocument();
    expect(screen.getByText("DEMO-VENCIDA")).toBeInTheDocument();
    expect(screen.getByText("Vigente", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("Vencida", { exact: true })).toBeInTheDocument();
    const acreditacionVencida = screen.getByText("DEMO-VENCIDA").closest("details");
    expect(acreditacionVencida).not.toHaveAttribute("open");
    await userEvent.click(screen.getByText("DEMO-VENCIDA"));
    expect(acreditacionVencida).toHaveAttribute("open");
    expect(screen.getByText("La acreditación venció.")).toBeVisible();
    expect(screen.getByRole("list", { name: "Listado de acreditaciones" })).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("list", { name: "Listado de capacidades habilitadas" })).toHaveAttribute("tabindex", "0");
    const niveles = screen.getByRole("list", { name: "Niveles permitidos para Ambulancias" });
    expect(within(niveles).getByText("Bajo")).toBeInTheDocument();
    expect(within(niveles).getByText("Medio")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Otorgar|Renovar|Revocar/ }),
    ).not.toBeInTheDocument();
  });
  it("explica la ONG pendiente y el historial vacío sin otorgar competencia", async () => {
    server.use(
      http.get(`${base}/certificaciones`, () =>
        HttpResponse.json({
          ...perfil,
          estadoOng: "PENDIENTE",
          motivosInstitucionales: [
            {
              codigo: "ONG_PENDIENTE",
              mensaje: "La ONG tiene pendiente su habilitación institucional.",
              capacidadId: null,
            },
          ],
        }),
      ),
    );
    renderPage("certificaciones");
    expect(
      await screen.findByText("Pendiente de revisión"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Tu ONG todavía no tiene acreditaciones registradas."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Tu ONG no tiene capacidades habilitadas/),
    ).toBeInTheDocument();
  });
  it("permite reintentar una consulta fallida sin conservar un perfil habilitado", async () => {
    server.use(
      http.get(`${base}/certificaciones`, () =>
        HttpResponse.json(
          { detail: "El Sistema Nacional demoró en responder." },
          { status: 504 },
        ),
      ),
    );
    renderPage("certificaciones");
    expect(
      await screen.findByText("El Sistema Nacional demoró en responder."),
    ).toBeInTheDocument();
    server.use(
      http.get(`${base}/certificaciones`, () => HttpResponse.json(perfil)),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Actualizar certificaciones" }),
    );
    expect(
      await screen.findByText("Habilitada"),
    ).toBeInTheDocument();
  });
  it("muestra revisión administrativa ante revocación del acceso", async () => {
    server.use(
      http.get(`${base}/certificaciones`, () => {
        conectada = false;
        return HttpResponse.json(
          { detail: "La credencial nacional expiró." },
          { status: 401 },
        );
      }),
    );
    renderPage("certificaciones");
    expect(
      await screen.findByRole("heading", { name: "El acceso nacional requiere revisión" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Mis certificaciones" }),
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
    expect(screen.getByLabelText(/Nuevo total/)).toBeInTheDocument();
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
