import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { MisOfertasPage } from "./MisOfertasPage";

const API_URL = "http://localhost:8000/api/v1";

const oferta = {
  id: 9,
  convocatoria_id: 5,
  emergencia_id: 31,
  ong_creadora_id: 4,
  creada_por_usuario_id: 7,
  estado: "PRESENTADA",
  version_actual: 1,
  version_bloqueo: 1,
  editable: true,
  observaciones: "Donación inicial",
  presentada_en: "2026-09-19T18:20:39.102766Z",
  creada_en: "2026-09-19T18:20:39.102766Z",
  items: [
    {
      id: 1,
      lote_id: 12,
      tipo: "RECURSO",
      descripcion: "Bidones de agua potable",
      cantidad_ofrecida: "500.000",
      unidad: "litros",
    },
  ],
  emergencia: {
    zona: "Ribera norte",
    gravedad: "ALTA",
    descripcion: "Inundación con familias evacuadas.",
  },
};

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderPage(): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  queryClient.setQueryData(["session"], {
    usuario: { id: 7, email: "ong@example.test", rol: "REPRESENTANTE_ONG",
      organizacion: { id: 4, nombre: "Mi ONG", tipo: "ONG" }, requiere_cambio_password: false },
    csrf_token: "csrf-local",
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <MisOfertasPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MisOfertasPage", () => {
  it("indica la carga mientras consulta las ofertas", async () => {
    let resolver: ((valor: Response) => void) | undefined;
    const pendiente = new Promise<Response>((resolve) => {
      resolver = resolve;
    });
    server.use(http.get(`${API_URL}/ofertas`, () => pendiente));
    renderPage();

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Cargando tus ofertas…",
    );

    resolver?.(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  it("muestra el estado vacío sin ofertas presentadas", async () => {
    server.use(http.get(`${API_URL}/ofertas`, () => HttpResponse.json([])));
    renderPage();

    expect(
      await screen.findByText("Todavía no presentaste ofertas."),
    ).toBeInTheDocument();
  });

  it("lista las ofertas propias con el contexto de la emergencia, sin ids", async () => {
    server.use(http.get(`${API_URL}/ofertas`, () => HttpResponse.json([oferta])));
    renderPage();

    expect(await screen.findByText("Alta · Ribera norte")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Mis ofertas" })).getByText("Presentada")).toBeInTheDocument();
    expect(screen.queryByText(/Oferta N/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Convocatoria N/)).not.toBeInTheDocument();

    await userEvent.setup().click(screen.getByText("Alta · Ribera norte"));

    expect(screen.getByText("Donación inicial")).toBeInTheDocument();
    expect(
      screen.getByText(/Bidones de agua potable — 500,00 litros \(Recurso\)/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/lote N/)).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Modificar oferta" }),
    ).toHaveAttribute("href", "/ofertas/9/editar");
  });

  it("combina la búsqueda por aporte con el estado de la oferta", async () => {
    server.use(http.get(`${API_URL}/ofertas`, ({ request }) => {
      const params = new URL(request.url).searchParams;
      return HttpResponse.json(params.get("q") === "bidones" && params.get("estado") === "PRESENTADA" ? [oferta] : []);
    }));
    renderPage();
    const user = userEvent.setup();
    await user.type(screen.getByRole("searchbox", { name: "Buscar ofertas" }), "bidones");
    const estado = screen.getByRole("combobox", { name: "Estado de la oferta" });
    await user.selectOptions(estado, "PRESENTADA");
    expect(await screen.findByText("Alta · Ribera norte")).toBeInTheDocument();
    await user.selectOptions(estado, "ADJUDICADA");
    expect(await screen.findByText(/No encontramos ofertas/)).toBeInTheDocument();
  });

  it("muestra el error accionable y permite reintentar", async () => {
    let intentos = 0;
    server.use(
      http.get(`${API_URL}/ofertas`, () => {
        intentos += 1;
        if (intentos === 1) {
          return HttpResponse.json({ detail: "Falla temporal." }, { status: 500 });
        }
        return HttpResponse.json([oferta]);
      }),
    );
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Falla temporal.");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("Alta · Ribera norte")).toBeInTheDocument();
    expect(intentos).toBe(2);
  });

  it("muestra la oferta conjunta deshabilitada cuando faltan recursos nacionales", async () => {
    server.use(http.get(`${API_URL}/ofertas`, () => HttpResponse.json([oferta])));
    renderPage();
    await userEvent.setup().click(await screen.findByText("Alta · Ribera norte"));
    expect(screen.getByRole("heading", { name: "Oferta conjunta" })).toBeVisible();
    const invitar = screen.getByRole("button", { name: "Invitar ONGs" });
    expect(invitar).toBeDisabled();
    expect(invitar).toHaveAccessibleDescription(/recursos del inventario nacional/i);
  });

  it("mantiene modificar oferta deshabilitado y explica el plazo al finalizar la convocatoria", async () => {
    server.use(http.get(`${API_URL}/ofertas`, () => HttpResponse.json([{ ...oferta, editable: false }])));
    renderPage();
    await userEvent.setup().click(await screen.findByText("Alta · Ribera norte"));
    expect(screen.queryByRole("link", { name: "Modificar oferta" })).not.toBeInTheDocument();
    const modificar = screen.getByRole("button", { name: "Modificar oferta" });
    expect(modificar).toBeDisabled();
    expect(modificar).toHaveAccessibleDescription(/convocatoria.*abierta/i);
  });

  it("explica que hay que desarmar el consorcio antes de editar aportes", async () => {
    server.use(http.get(`${API_URL}/ofertas`, () => HttpResponse.json([{
      ...oferta, editable: false, consorcio_editable: true, requiere_desglose_nacional: true,
      participantes: [
        { ong_id: 4, nombre: "Mi ONG", rol: "LIDER", confirmada: true },
        { ong_id: 5, nombre: "Otra ONG", rol: "MIEMBRO", confirmada: true },
      ],
    }])));
    renderPage();
    await userEvent.setup().click(await screen.findByText("Alta · Ribera norte"));
    const modificar = screen.getByRole("button", { name: "Modificar oferta" });
    expect(modificar).toBeDisabled();
    expect(modificar).toHaveAccessibleDescription(/desarmá el consorcio/i);
  });
});
