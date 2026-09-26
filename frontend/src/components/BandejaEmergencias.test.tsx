import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { BandejaEmergencias } from "./BandejaEmergencias";

const API_URL = "http://localhost:8000/api/v1";

const emergenciaBase = {
  id: 31,
  municipio_id: 1,
  centro_coordinador_id: null,
  creada_por_usuario_id: 1,
  gravedad: "ALTA",
  zona: "Ribera norte",
  descripcion: "Inundación con familias evacuadas y acceso restringido.",
  estado: "REGISTRADA",
  bonita_sync: "PENDIENTE",
  bonita_process_instance_id: null,
  creada_en: "2026-09-19T18:20:39.102766Z",
  actualizada_en: "2026-09-19T18:20:39.102766Z",
  cantidad_lotes_borrador: 0,
};

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderBandeja(rol: "OPERADOR_MUNICIPAL" | "COORDINADOR_REGIONAL"): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <BandejaEmergencias rol={rol} csrfToken="csrf-de-prueba" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BandejaEmergencias", () => {
  it("indica la carga mientras consulta la bandeja", async () => {
    let resolver: ((valor: Response) => void) | undefined;
    const pendiente = new Promise<Response>((resolve) => {
      resolver = resolve;
    });
    server.use(http.get(`${API_URL}/emergencias`, () => pendiente));
    renderBandeja("OPERADOR_MUNICIPAL");

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Cargando emergencias…",
    );

    resolver?.(
      new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await waitFor(() => {
      expect(screen.getByText("Todavía no registraste emergencias.")).toBeInTheDocument();
    });
  });

  it("muestra el estado vacío para un municipio sin emergencias", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () => HttpResponse.json([], { status: 200 })),
    );
    renderBandeja("OPERADOR_MUNICIPAL");

    expect(
      await screen.findByText("Todavía no registraste emergencias."),
    ).toBeInTheDocument();
  });

  it("muestra el estado vacío para un centro coordinador sin pendientes", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () => HttpResponse.json([], { status: 200 })),
    );
    renderBandeja("COORDINADOR_REGIONAL");

    expect(
      await screen.findByText("No hay emergencias registradas pendientes."),
    ).toBeInTheDocument();
  });

  it("lista las emergencias devueltas con su estado y gravedad", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json(
          [
            emergenciaBase,
            { ...emergenciaBase, id: 32, zona: "Corredor Norte", gravedad: "MEDIA", estado: "EN_COORDINACION" },
          ],
          { status: 200 },
        ),
      ),
    );
    renderBandeja("OPERADOR_MUNICIPAL");

    expect(await screen.findByText("Alta · Ribera norte")).toBeInTheDocument();
    expect(screen.getByText("Registrada")).toBeInTheDocument();
    expect(screen.getByText("Media · Corredor Norte")).toBeInTheDocument();
    expect(screen.getByText("En coordinación")).toBeInTheDocument();
  });

  it("muestra el detalle de una emergencia al expandirla", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json([emergenciaBase], { status: 200 }),
      ),
    );
    const user = userEvent.setup();
    renderBandeja("OPERADOR_MUNICIPAL");

    const resumen = await screen.findByText("Alta · Ribera norte");
    expect(
      screen.queryByText(
        "Inundación con familias evacuadas y acceso restringido.",
      ),
    ).not.toBeVisible();

    await user.click(resumen);

    expect(
      screen.getByText("Inundación con familias evacuadas y acceso restringido."),
    ).toBeVisible();
  });

  it("ofrece generar lotes solo al centro coordinador", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json([emergenciaBase], { status: 200 }),
      ),
    );
    const user = userEvent.setup();
    renderBandeja("COORDINADOR_REGIONAL");

    await user.click(await screen.findByText("Alta · Ribera norte"));

    expect(screen.getByRole("link", { name: "Generar lotes" })).toHaveAttribute(
      "href",
      "/emergencias/31/lotes",
    );
  });

  it("no ofrece generar lotes al municipio", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json([emergenciaBase], { status: 200 }),
      ),
    );
    const user = userEvent.setup();
    renderBandeja("OPERADOR_MUNICIPAL");

    await user.click(await screen.findByText("Alta · Ribera norte"));

    expect(
      screen.queryByRole("link", { name: "Generar lotes" }),
    ).not.toBeInTheDocument();
  });

  it("publica desde la lista cuando la emergencia ya tiene lotes en borrador", async () => {
    let publicada = false;
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json(
          publicada ? [] : [{ ...emergenciaBase, cantidad_lotes_borrador: 2 }],
          { status: 200 },
        ),
      ),
      http.post(`${API_URL}/emergencias/31/publicar`, () => {
        publicada = true;
        return HttpResponse.json(
          {
            id: 4,
            emergencia_id: 31,
            numero: 1,
            estado: "ABIERTA",
            publicada_en: "2026-09-19T18:20:39.102766Z",
            cierra_en: "2026-09-19T20:20:39.102766Z",
            lotes: [
              { lote_id: 7, cantidad_publicada: "500.000", unidad_publicada: "litros" },
              { lote_id: 8, cantidad_publicada: "40.000", unidad_publicada: "unidades" },
            ],
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderBandeja("COORDINADOR_REGIONAL");

    await user.click(await screen.findByText("Alta · Ribera norte"));

    expect(screen.getByText(/Al publicar, los 2 lotes en borrador/)).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Publicar convocatoria" }),
    );
    await user.click(screen.getByRole("button", { name: "Sí, publicar" }));

    expect(
      await screen.findByText("Convocatoria N.º 1 publicada"),
    ).toBeInTheDocument();
    // Al publicar, la emergencia sale de la bandeja del coordinador.
    await waitFor(() => {
      expect(
        screen.getByText("No hay emergencias registradas pendientes."),
      ).toBeInTheDocument();
    });
  });

  it("no ofrece publicar en la lista si la emergencia no tiene lotes", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json([emergenciaBase], { status: 200 }),
      ),
    );
    const user = userEvent.setup();
    renderBandeja("COORDINADOR_REGIONAL");

    await user.click(await screen.findByText("Alta · Ribera norte"));

    expect(screen.getByRole("link", { name: "Generar lotes" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Publicar convocatoria" }),
    ).not.toBeInTheDocument();
  });

  it("muestra el error accionable cuando falla la consulta", async () => {
    server.use(
      http.get(`${API_URL}/emergencias`, () =>
        HttpResponse.json(
          { detail: "Solo un municipio activo puede consultar sus emergencias." },
          { status: 403 },
        ),
      ),
    );
    renderBandeja("OPERADOR_MUNICIPAL");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Solo un municipio activo puede consultar sus emergencias.",
    );
  });

  it("reintenta la consulta al usar el botón de reintentar", async () => {
    let intentos = 0;
    server.use(
      http.get(`${API_URL}/emergencias`, () => {
        intentos += 1;
        if (intentos === 1) {
          return HttpResponse.json({ detail: "Falla temporal." }, { status: 500 });
        }
        return HttpResponse.json([emergenciaBase], { status: 200 });
      }),
    );
    const user = userEvent.setup();
    renderBandeja("OPERADOR_MUNICIPAL");

    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("Alta · Ribera norte")).toBeInTheDocument();
    expect(intentos).toBe(2);
  });
});
