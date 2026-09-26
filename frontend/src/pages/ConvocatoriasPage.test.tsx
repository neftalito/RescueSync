import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { ConvocatoriasPage } from "./ConvocatoriasPage";

const API_URL = "http://localhost:8000/api/v1";
const URL_CONVOCATORIAS = `${API_URL}/convocatorias`;

const abierta = {
  id: 4,
  emergencia_id: 31,
  numero: 1,
  estado: "ABIERTA",
  publicada_en: "2026-09-19T18:20:39.102766Z",
  cierra_en: "2026-09-19T20:20:39.102766Z",
  cantidad_lotes: 2,
  gravedad: "ALTA",
  zona: "Ribera norte",
};

const cerrada = {
  id: 5,
  emergencia_id: 32,
  numero: 2,
  estado: "CERRADA",
  publicada_en: "2026-09-10T10:00:00.000000Z",
  cierra_en: "2026-09-11T10:00:00.000000Z",
  cantidad_lotes: 1,
  gravedad: "BAJA",
  zona: "Barrio sur",
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
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ConvocatoriasPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ConvocatoriasPage", () => {
  it("lista las convocatorias del centro con su estado y ventana", async () => {
    const rutas: string[] = [];
    server.use(
      http.get(URL_CONVOCATORIAS, ({ request }) => {
        rutas.push(request.url);
        return HttpResponse.json({ items: [abierta, cerrada] });
      }),
    );
    renderPage();

    expect(
      await screen.findByRole("heading", { name: "Convocatoria N.º 1" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Convocatoria N.º 2" }),
    ).toBeInTheDocument();
    // Se consulta dentro de la lista: las opciones del filtro usan las mismas
    // etiquetas que las insignias de estado.
    const lista = within(screen.getByRole("list"));
    expect(lista.getByText("Ribera norte · Gravedad Alta")).toBeInTheDocument();
    expect(lista.getByText("Barrio sur · Gravedad Baja")).toBeInTheDocument();
    expect(lista.getByText("Abierta")).toBeInTheDocument();
    expect(lista.getByText("Cerrada")).toBeInTheDocument();
    expect(rutas).toEqual([URL_CONVOCATORIAS]);
    const enlaces = lista.getAllByRole("link", {
      name: "Ver lotes de la emergencia",
    });
    expect(enlaces.map((enlace) => enlace.getAttribute("href"))).toEqual([
      "/emergencias/31/lotes",
      "/emergencias/32/lotes",
    ]);
  });

  it("filtra el listado por estado", async () => {
    const rutas: string[] = [];
    server.use(
      http.get(URL_CONVOCATORIAS, ({ request }) => {
        rutas.push(request.url);
        return request.url.includes("estado=ABIERTA")
          ? HttpResponse.json({ items: [abierta] })
          : HttpResponse.json({ items: [abierta, cerrada] });
      }),
    );
    const user = userEvent.setup();
    renderPage();

    await screen.findByRole("heading", { name: "Convocatoria N.º 2" });
    await user.selectOptions(screen.getByLabelText("Estado"), "ABIERTA");

    await screen.findByRole("heading", { name: "Convocatoria N.º 1" });
    expect(
      screen.queryByRole("heading", { name: "Convocatoria N.º 2" }),
    ).not.toBeInTheDocument();
    expect(rutas).toEqual([
      URL_CONVOCATORIAS,
      `${URL_CONVOCATORIAS}?estado=ABIERTA`,
    ]);
  });

  it("explica cómo empezar cuando el centro todavía no publicó nada", async () => {
    server.use(http.get(URL_CONVOCATORIAS, () => HttpResponse.json({ items: [] })));
    renderPage();

    expect(await screen.findByText(/Todavía no publicaste/)).toBeInTheDocument();
  });

  it("distingue el vacío de un filtro sin resultados", async () => {
    server.use(
      http.get(URL_CONVOCATORIAS, ({ request }) =>
        HttpResponse.json(
          { items: request.url.includes("estado=CANCELADA") ? [] : [abierta] },
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage();

    await screen.findByRole("heading", { name: "Convocatoria N.º 1" });
    await user.selectOptions(screen.getByLabelText("Estado"), "CANCELADA");

    expect(
      await screen.findByText(/No tenés convocatorias en estado Cancelada/),
    ).toBeInTheDocument();
  });

  it("muestra el error de la API con opción de reintentar", async () => {
    let intentos = 0;
    server.use(
      http.get(URL_CONVOCATORIAS, () => {
        intentos += 1;
        return intentos === 1
          ? HttpResponse.json({ detail: "Tu sesión expiró." }, { status: 401 })
          : HttpResponse.json({ items: [abierta] });
      }),
    );
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Tu sesión expiró.",
    );

    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(
      await screen.findByRole("heading", { name: "Convocatoria N.º 1" }),
    ).toBeInTheDocument();
  });
});
