import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse, ws } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import App from "../App";
import type { Session } from "../schemas/auth";
import type { EmergenciaEnBandeja } from "../schemas/emergencia";

const API_URL = "http://localhost:8000/api/v1";
const capacidadId = "00000000-0000-4000-8000-000000000101";
const session: Session = {
  usuario: {
    id: 2,
    email: "coordinador@rescuesync.org",
    rol: "COORDINADOR_REGIONAL",
    organizacion: { id: 3, nombre: "Centro Norte", tipo: "CENTRO_COORDINADOR" },
    requiere_cambio_password: false,
  },
  csrf_token: "csrf-firmado",
};
const emergencia: EmergenciaEnBandeja = {
  id: 31,
  municipio_id: 1,
  centro_coordinador_id: 3,
  creada_por_usuario_id: 1,
  gravedad: "ALTA",
  zona: "Sin lotes",
  prioridad: null,
  descripcion: "Familias evacuadas por la inundación.",
  estado: "REGISTRADA",
  tiene_lotes: false,
  bonita_sync: "VINCULADA",
  bonita_process_instance_id: 1001,
  bonita_ultimo_error: null,
  bonita_ultimo_intento_en: null,
  creada_en: "2026-09-19T18:20:39.102766Z",
  actualizada_en: "2026-09-19T18:20:39.102766Z",
};
const emergencias: EmergenciaEnBandeja[] = [
  emergencia,
  { ...emergencia, id: 32, zona: "Borradores", tiene_lotes: true },
  { ...emergencia, id: 33, zona: "Convocatoria abierta", estado: "PUBLICADA", tiene_lotes: true },
  { ...emergencia, id: 34, zona: "Coordinación sin lotes", estado: "EN_COORDINACION" },
];
const server = setupServer(
  ws.link("ws://localhost:8000/api/v1/notificaciones/ws").addEventListener("connection", () => {}),
  http.get(`${API_URL}/auth/me`, () => HttpResponse.json(session)),
  http.get(`${API_URL}/notificaciones`, () => HttpResponse.json([])),
  http.get(`${API_URL}/emergencias`, () => HttpResponse.json(emergencias)),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderPage(path: string): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}><App /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Emergencias del coordinador", () => {
  it("presenta dos tarjetas y consulta las emergencias al abrir cada vista", async () => {
    let consultas = 0;
    server.use(http.get(`${API_URL}/emergencias`, () => {
      consultas++;
      return HttpResponse.json(emergencias);
    }));
    const user = userEvent.setup();
    renderPage("/");
    const pendientes = await screen.findByRole("link", { name: "Ver emergencias pendientes" });
    expect(pendientes.closest("article")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver emergencias no pendientes" }).closest("article")).toBeInTheDocument();
    expect(consultas).toBe(0);
    expect(screen.queryByText("Alta · Sin lotes")).not.toBeInTheDocument();

    await user.click(pendientes);
    expect(await screen.findByText("Alta · Sin lotes")).toBeInTheDocument();
    expect(screen.getByText("Alta · Coordinación sin lotes")).toBeInTheDocument();
    expect(screen.queryByText("Alta · Borradores")).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Volver al inicio" }));
    await user.click(await screen.findByRole("link", { name: "Ver emergencias no pendientes" }));
    expect(await screen.findByText("Alta · Borradores")).toBeInTheDocument();
    expect(screen.getByText("Alta · Convocatoria abierta")).toBeInTheDocument();
    expect(screen.queryByText("Alta · Sin lotes")).not.toBeInTheDocument();
    expect(screen.queryByText("Alta · Coordinación sin lotes")).not.toBeInTheDocument();
  });

  it("filtra las emergencias con lotes por estado, incluso si siguen registradas", async () => {
    const user = userEvent.setup();
    renderPage("/emergencias/con-lotes");
    await screen.findByText("Alta · Borradores");
    const filtro = screen.getByRole("combobox", { name: "Estado de la emergencia" });
    await user.selectOptions(filtro, "REGISTRADA");
    expect(screen.getByText("Alta · Borradores")).toBeInTheDocument();
    expect(screen.queryByText("Alta · Sin lotes")).not.toBeInTheDocument();
    expect(screen.queryByText("Alta · Convocatoria abierta")).not.toBeInTheDocument();
    await user.click(screen.getByText("Alta · Borradores"));
    expect(screen.getByRole("link", { name: "Ver lotes" })).toHaveAttribute("href", "/emergencias/32/lotes");
    await user.selectOptions(filtro, "PUBLICADA");
    expect(screen.getByText("Alta · Convocatoria abierta")).toBeInTheDocument();
    expect(screen.queryByText("Alta · Borradores")).not.toBeInTheDocument();
    await user.selectOptions(filtro, "RESUELTA");
    expect(screen.getByRole("status")).toHaveTextContent("No hay emergencias con lotes en el estado seleccionado.");
    await user.selectOptions(filtro, "");
    expect(screen.getByText("Alta · Borradores")).toBeInTheDocument();
    expect(screen.getByText("Alta · Convocatoria abierta")).toBeInTheDocument();
  });

  it("restaura el filtro de la URL al abrir la vista directamente", async () => {
    renderPage("/emergencias/con-lotes?estado=PUBLICADA");
    expect(await screen.findByText("Alta · Convocatoria abierta")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveValue("PUBLICADA");
    expect(screen.queryByText("Alta · Borradores")).not.toBeInTheDocument();
  });

  it("mueve una emergencia a no pendientes al guardar el primer lote sin cambiar su estado", async () => {
    let conLotes = false;
    const lote = {
      id: 7, emergencia_id: 31, creado_por_usuario_id: 2,
      tipo_necesidad: "Agua potable", capacidad_nacional_id: capacidadId,
      cantidad_requerida: "100.000", unidad: "litros", descripcion: null,
      estado: "BORRADOR", version: 1,
      creado_en: emergencia.creada_en, actualizado_en: emergencia.actualizada_en,
    };
    server.use(
      http.get(`${API_URL}/emergencias`, () => HttpResponse.json([{ ...emergencia, tiene_lotes: conLotes }])),
      http.get(`${API_URL}/emergencias/31/lotes`, () => HttpResponse.json(conLotes ? [lote] : [])),
      http.get(`${API_URL}/emergencias/catalogos/capacidades-nacionales`, () => HttpResponse.json([{
        id: capacidadId, codigo: "AGUA", nombre: "Agua potable", tipo: "SUMINISTRO",
        unidad: "litros", admiteFracciones: true,
      }])),
      http.post(`${API_URL}/emergencias/31/lotes`, () => {
        conLotes = true;
        return HttpResponse.json([lote]);
      }),
      http.delete(`${API_URL}/emergencias/31/lotes/7`, () => {
        conLotes = false;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderPage("/emergencias/pendientes");
    await user.click(await screen.findByText("Alta · Sin lotes"));
    await user.click(screen.getByRole("link", { name: "Generar lotes" }));
    await screen.findByRole("option", { name: "Agua potable" });
    await user.selectOptions(screen.getByLabelText("Capacidad"), capacidadId);
    await user.type(screen.getByLabelText("Cantidad requerida"), "100");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));
    await screen.findByText("1 lote guardado en borrador.");
    await user.click(screen.getByRole("link", { name: "Volver al inicio" }));
    await user.click(await screen.findByRole("link", { name: "Ver emergencias pendientes" }));
    expect(await screen.findByRole("status")).toHaveTextContent("No hay emergencias pendientes sin lotes.");
    await user.click(screen.getByRole("link", { name: "Volver al inicio" }));
    await user.click(await screen.findByRole("link", { name: "Ver emergencias no pendientes" }));
    expect(await screen.findByText("Alta · Sin lotes")).toBeInTheDocument();
    expect(screen.getByText("Registrada", { selector: "span" })).toBeInTheDocument();
    await user.click(screen.getByText("Alta · Sin lotes"));
    await user.click(screen.getByRole("link", { name: "Ver lotes" }));
    await user.click(await screen.findByRole("button", { name: "Eliminar lote 1" }));
    await user.click(screen.getByRole("button", { name: "Sí, eliminar lote 1" }));
    await screen.findByText("Lote eliminado definitivamente.");
    await user.click(screen.getByRole("link", { name: "Volver al inicio" }));
    await user.click(await screen.findByRole("link", { name: "Ver emergencias pendientes" }));
    expect(await screen.findByText("Alta · Sin lotes")).toBeInTheDocument();
  });
});
