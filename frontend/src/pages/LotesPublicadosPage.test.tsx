import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { LotesPublicadosPage } from "./LotesPublicadosPage";
import { NuevaOfertaPage } from "./NuevaOfertaPage";

const API_URL = "http://localhost:8000/api/v1";

const lotePublicado = {
  id: 12,
  emergencia_id: 31,
  creado_por_usuario_id: 2,
  tipo_necesidad: "Agua potable",
  descripcion: "Bidones de 5 litros",
  cantidad_requerida: "1000.000",
  unidad: "litros",
  estado: "PUBLICADO",
  version: 1,
  creado_en: "2026-09-19T18:20:39.102766Z",
  actualizado_en: "2026-09-19T18:20:39.102766Z",
};

const convocatoria = {
  id: 8,
  emergencia_id: 31,
  numero: 1,
  estado: "ABIERTA",
  publicada_en: "2026-09-19T18:20:39.102766Z",
  cierra_en: "2026-09-20T18:20:39.102766Z",
  emergencia: { zona: "Ribera norte", gravedad: "ALTA", descripcion: "Inundación" },
  lotes: [{ lote_id: 12, tipo_necesidad: "Agua potable", descripcion: null,
    cantidad_publicada: "1000.000", unidad_publicada: "litros" }],
};

const ofertaExistente = {
  id: 92,
  convocatoria_id: 8,
  emergencia_id: 31,
  ong_creadora_id: 5,
  creada_por_usuario_id: 7,
  estado: "PRESENTADA",
  version_actual: 1,
  version_bloqueo: 1,
  editable: true,
  observaciones: null,
  presentada_en: "2026-09-19T18:20:39.102766Z",
  creada_en: "2026-09-19T18:20:39.102766Z",
  items: [{ id: 111, lote_id: 12, tipo: "RECURSO", descripcion: "Agua potable",
    cantidad_ofrecida: "250", unidad: "litros" }],
  emergencia: convocatoria.emergencia,
};

const server = setupServer(
  http.get(`${API_URL}/ofertas`, () => HttpResponse.json([])),
  http.get(`${API_URL}/convocatorias`, () => HttpResponse.json([convocatoria])),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderPage(ruta: string): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[ruta]}>
        <Routes>
          <Route
            path="/emergencias/:emergenciaId/lotes"
            element={<LotesPublicadosPage />}
          />
          <Route
            path="/ofertas/nueva"
            element={<NuevaOfertaPage csrfToken="csrf-firmado" />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LotesPublicadosPage", () => {
  it("indica la carga mientras consulta los lotes", async () => {
    let resolver: ((valor: Response) => void) | undefined;
    const pendiente = new Promise<Response>((resolve) => {
      resolver = resolve;
    });
    server.use(http.get(`${API_URL}/emergencias/31/lotes`, () => pendiente));
    renderPage("/emergencias/31/lotes");

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Cargando lotes…",
    );

    resolver?.(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  });

  it("muestra el estado vacío sin lotes publicados", async () => {
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () => HttpResponse.json([])),
    );
    renderPage("/emergencias/31/lotes");

    expect(
      await screen.findByText("Esta convocatoria todavía no tiene lotes publicados."),
    ).toBeInTheDocument();
  });

  it("lista los lotes publicados con cantidad, unidad y estado", async () => {
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () =>
        HttpResponse.json([lotePublicado]),
      ),
    );
    renderPage("/emergencias/31/lotes");

    expect(await screen.findByText("Agua potable")).toBeInTheDocument();
    expect(screen.getByText("1.000,00 litros")).toBeInTheDocument();
    expect(screen.getByText("Publicado")).toBeInTheDocument();
    expect(screen.getByText("Bidones de 5 litros")).toBeInTheDocument();
  });

  it("muestra el error accionable y permite reintentar", async () => {
    let intentos = 0;
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () => {
        intentos += 1;
        if (intentos === 1) {
          return HttpResponse.json({ detail: "Falla temporal." }, { status: 500 });
        }
        return HttpResponse.json([lotePublicado]);
      }),
    );
    const user = userEvent.setup();
    renderPage("/emergencias/31/lotes");

    expect(await screen.findByRole("alert")).toHaveTextContent("Falla temporal.");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("Agua potable")).toBeInTheDocument();
    expect(intentos).toBe(2);
  });

  it("permite crear una oferta desde el lote elegido con su convocatoria y lote precargados", async () => {
    let cuerpo: unknown;
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () =>
        HttpResponse.json([
          lotePublicado,
          { ...lotePublicado, id: 13, tipo_necesidad: "Alimentos" },
        ]),
      ),
      http.get(`${API_URL}/convocatorias`, () => HttpResponse.json([
        {
          id: 8,
          emergencia_id: 31,
          numero: 1,
          estado: "ABIERTA",
          publicada_en: "2026-09-19T18:20:39.102766Z",
          cierra_en: "2026-09-20T18:20:39.102766Z",
          emergencia: {
            zona: "Ribera norte",
            gravedad: "ALTA",
            descripcion: "Inundación",
          },
          lotes: [
            { lote_id: 12, tipo_necesidad: "Agua potable", descripcion: null, cantidad_publicada: "1000.000", unidad_publicada: "litros" },
            { lote_id: 13, tipo_necesidad: "Alimentos", descripcion: null, cantidad_publicada: "1000.000", unidad_publicada: "raciones" },
          ],
        },
      ])),
      http.get(`${API_URL}/ofertas`, () => HttpResponse.json([])),
      http.post(`${API_URL}/ofertas`, async ({ request }) => {
        cuerpo = await request.json();
        return HttpResponse.json({
          id: 92,
          convocatoria_id: 8,
          emergencia_id: 31,
          ong_creadora_id: 5,
          creada_por_usuario_id: 7,
          estado: "PRESENTADA",
          version_actual: 1,
          version_bloqueo: 1,
          editable: true,
          observaciones: null,
          presentada_en: "2026-09-19T18:20:39.102766Z",
          creada_en: "2026-09-19T18:20:39.102766Z",
          items: [{ id: 111, lote_id: 13, tipo: "RECURSO", descripcion: "Alimentos", cantidad_ofrecida: "250", unidad: "raciones" }],
        }, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPage("/emergencias/31/lotes");

    const enlace = await screen.findByRole("link", { name: "Crear oferta para Alimentos" });
    expect(enlace).toHaveAttribute("href", "/ofertas/nueva?loteId=13");
    await user.click(enlace);

    expect(await screen.findByLabelText("Convocatoria")).toHaveValue("8");
    expect(screen.getByRole("group", { name: "Alimentos" })).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Agua potable" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("Cantidad ofrecida")).toHaveValue("");

    await user.type(screen.getByLabelText("Cantidad ofrecida"), "250");
    await user.click(screen.getByRole("button", { name: "Presentar oferta" }));

    await waitFor(() => expect(cuerpo).toEqual({
      convocatoria_id: 8,
      observaciones: null,
      items: [{ lote_id: 13, tipo: "RECURSO", descripcion: "Alimentos", cantidad_ofrecida: "250", unidad: "raciones" }],
    }));
    expect(await screen.findByRole("status")).toHaveTextContent("Oferta 92 presentada correctamente.");
  });

  it("rechaza un identificador de emergencia inválido sin consultar la API", () => {
    server.use(
      http.get(`${API_URL}/emergencias/:id/lotes`, () => {
        throw new Error("no debería consultarse con un id inválido");
      }),
    );
    renderPage("/emergencias/abc/lotes");

    expect(
      screen.getByText("El identificador de emergencia no es válido."),
    ).toBeInTheDocument();
  });

  it("mantiene crear oferta deshabilitado y explica que la ONG ya ofertó el lote", async () => {
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () => HttpResponse.json([lotePublicado])),
      http.get(`${API_URL}/ofertas`, () => HttpResponse.json([ofertaExistente])),
    );
    renderPage("/emergencias/31/lotes");

    const crear = await screen.findByRole("button", { name: "Crear oferta para Agua potable" });
    await waitFor(() => expect(crear).toHaveAccessibleDescription(/ya.*oferta para este lote/i));
    expect(crear).toBeDisabled();
    expect(screen.queryByRole("link", { name: "Crear oferta para Agua potable" })).not.toBeInTheDocument();
    await userEvent.setup().click(crear);
    expect(screen.getByRole("heading", { name: "Lotes publicados" })).toBeInTheDocument();
  });

  it("explica que para sumar otro lote de la misma convocatoria hay que editar la oferta existente", async () => {
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () => HttpResponse.json([lotePublicado])),
      http.get(`${API_URL}/ofertas`, () => HttpResponse.json([{
        ...ofertaExistente, items: [{ ...ofertaExistente.items[0], lote_id: 13 }],
      }])),
    );
    renderPage("/emergencias/31/lotes");

    const crear = await screen.findByRole("button", { name: "Crear oferta para Agua potable" });
    await waitFor(() => expect(crear).toHaveAccessibleDescription(/agregar este lote.*modificá/i));
    expect(crear).toBeDisabled();
  });

  it("no bloquea una convocatoria nueva por una oferta del mismo lote en una ronda anterior", async () => {
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () => HttpResponse.json([lotePublicado])),
      http.get(`${API_URL}/ofertas`, () => HttpResponse.json([{
        ...ofertaExistente, convocatoria_id: 7, editable: false,
      }])),
    );
    renderPage("/emergencias/31/lotes");

    expect(await screen.findByRole("link", { name: "Crear oferta para Agua potable" }))
      .toHaveAttribute("href", "/ofertas/nueva?loteId=12");
  });

  it("reconoce la oferta conjunta de la ONG aunque otra participante la haya creado", async () => {
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () => HttpResponse.json([lotePublicado])),
      http.get(`${API_URL}/ofertas`, () => HttpResponse.json([{
        ...ofertaExistente, ong_creadora_id: 6, editable: false, consorcio_editable: true,
        participantes: [
          { ong_id: 6, nombre: "Otra ONG", rol: "LIDER", confirmada: true },
          { ong_id: 5, nombre: "Mi ONG", rol: "MIEMBRO", confirmada: true },
        ],
      }])),
    );
    renderPage("/emergencias/31/lotes");

    const crear = await screen.findByRole("button", { name: "Crear oferta para Agua potable" });
    await waitFor(() => expect(crear).toHaveAccessibleDescription(/ya.*oferta para este lote/i));
    expect(crear).toBeDisabled();
  });

  it("espera a verificar las ofertas antes de habilitar crear oferta", async () => {
    let resolver: ((respuesta: Response) => void) | undefined;
    const pendiente = new Promise<Response>((resolve) => { resolver = resolve; });
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () => HttpResponse.json([lotePublicado])),
      http.get(`${API_URL}/ofertas`, () => pendiente),
    );
    renderPage("/emergencias/31/lotes");

    const crear = await screen.findByRole("button", { name: "Crear oferta para Agua potable" });
    expect(crear).toBeDisabled();
    expect(crear).toHaveAccessibleDescription(/verificando/i);
    resolver?.(HttpResponse.json([]));
    expect(await screen.findByRole("link", { name: "Crear oferta para Agua potable" })).toBeInTheDocument();
  });

  it("mantiene crear deshabilitado si falla la verificación de ofertas y permite reintentar", async () => {
    let intentos = 0;
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () => HttpResponse.json([lotePublicado])),
      http.get(`${API_URL}/ofertas`, () => {
        intentos += 1;
        return intentos === 1
          ? HttpResponse.json({ detail: "Falla temporal." }, { status: 500 })
          : HttpResponse.json([ofertaExistente]);
      }),
    );
    renderPage("/emergencias/31/lotes");

    expect(await screen.findByRole("alert")).toHaveTextContent(/No pudimos verificar/i);
    const crear = screen.getByRole("button", { name: "Crear oferta para Agua potable" });
    expect(crear).toBeDisabled();
    await userEvent.setup().click(screen.getByRole("button", { name: "Reintentar verificación" }));
    await waitFor(() => expect(crear).toHaveAccessibleDescription(/ya.*oferta para este lote/i));
    expect(crear).toBeDisabled();
    expect(intentos).toBe(2);
  });

  it("deshabilita crear si el lote ya no pertenece a una convocatoria abierta", async () => {
    server.use(
      http.get(`${API_URL}/emergencias/31/lotes`, () => HttpResponse.json([lotePublicado])),
      http.get(`${API_URL}/convocatorias`, () => HttpResponse.json([])),
    );
    renderPage("/emergencias/31/lotes");

    const crear = await screen.findByRole("button", { name: "Crear oferta para Agua potable" });
    await waitFor(() => expect(crear).toHaveAccessibleDescription(/convocatoria abierta/i));
    expect(crear).toBeDisabled();
  });
});
