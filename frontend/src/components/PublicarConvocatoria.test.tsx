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
  describe,
  expect,
  it,
  vi,
} from "vitest";

import type { EstadoLote, Lote } from "../schemas/lote";
import { PublicarConvocatoria } from "./PublicarConvocatoria";

const API_URL = "http://localhost:8000/api/v1";
const CSRF_TOKEN = "csrf-firmado";
const URL_PUBLICAR = `${API_URL}/emergencias/31/publicar`;

function lote(
  id: number,
  estado: EstadoLote = "BORRADOR",
): Lote {
  return {
    id,
    emergencia_id: 31,
    creado_por_usuario_id: 2,
    tipo_necesidad: "Agua potable",
    descripcion: null,
    cantidad_requerida: "500.000",
    unidad: "litros",
    estado,
    version: 1,
    creado_en: "2026-09-19T18:20:39.102766Z",
    actualizado_en: "2026-09-19T18:20:39.102766Z",
  };
}

function convocatoriaPublicada(): Record<string, unknown> {
  return {
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
  };
}

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderPanel(
  lotes: Lote[],
  publicada = false,
): QueryClient {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PublicarConvocatoria
          emergenciaId={31}
          csrfToken={CSRF_TOKEN}
          lotes={lotes}
          publicada={publicada}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return queryClient;
}

describe("PublicarConvocatoria", () => {
  it("publica los lotes en borrador con confirmación y token CSRF", async () => {
    let requestCredentials: RequestCredentials | undefined;
    let csrfHeader: string | null = null;
    server.use(
      http.post(URL_PUBLICAR, ({ request }) => {
        requestCredentials = request.credentials;
        csrfHeader = request.headers.get("X-CSRF-Token");
        return HttpResponse.json(convocatoriaPublicada(), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPanel([lote(7), lote(8)]);

    await user.click(
      screen.getByRole("button", { name: "Publicar convocatoria" }),
    );
    expect(screen.getByRole("group")).toHaveTextContent(
      "¿Publicar la convocatoria?",
    );

    await user.click(screen.getByRole("button", { name: "Sí, publicar" }));

    expect(await screen.findByText("Convocatoria N.º 1 publicada")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Se publicaron 2 lotes");
    expect(screen.getByRole("link", { name: "Ver convocatorias" })).toHaveAttribute(
      "href",
      "/convocatorias",
    );
    expect(requestCredentials).toBe("include");
    expect(csrfHeader).toBe(CSRF_TOKEN);
  });

  it("no publica nada si el coordinador cancela la confirmación", async () => {
    let publicaciones = 0;
    server.use(
      http.post(URL_PUBLICAR, () => {
        publicaciones += 1;
        return HttpResponse.json(convocatoriaPublicada(), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPanel([lote(7)]);

    await user.click(
      screen.getByRole("button", { name: "Publicar convocatoria" }),
    );
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(publicaciones).toBe(0);
    expect(
      screen.queryByRole("group", { name: /¿Publicar la convocatoria\?/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Publicar convocatoria" }),
    ).toBeInTheDocument();
  });

  it("no permite publicar sin lotes en borrador", () => {
    renderPanel([lote(7, "PUBLICADO")]);

    expect(
      screen.getByRole("button", { name: "Sin lotes en borrador" }),
    ).toBeDisabled();
    expect(
      screen.getByText("Guardá al menos un lote en borrador para poder publicar."),
    ).toBeInTheDocument();
  });

  it("no ofrece volver a publicar una convocatoria ya publicada", () => {
    renderPanel([lote(7, "PUBLICADO")], true);

    expect(
      screen.getByRole("button", { name: "Convocatoria publicada" }),
    ).toBeDisabled();
    expect(
      screen.getByText(/ya está publicada. Los lotes que agregues ahora/),
    ).toBeInTheDocument();
  });

  it("muestra el motivo del backend y permite reintentar", async () => {
    server.use(
      http.post(URL_PUBLICAR, () =>
        HttpResponse.json(
          { detail: "La emergencia no tiene lotes en borrador para publicar." },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderPanel([lote(7)]);

    await user.click(
      screen.getByRole("button", { name: "Publicar convocatoria" }),
    );
    await user.click(screen.getByRole("button", { name: "Sí, publicar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La emergencia no tiene lotes en borrador para publicar.",
    );
    expect(
      screen.getByRole("button", { name: "Publicar convocatoria" }),
    ).toBeInTheDocument();
  });

  it("invalida el listado y los lotes al publicar", async () => {
    server.use(
      http.post(URL_PUBLICAR, () =>
        HttpResponse.json(convocatoriaPublicada(), { status: 201 }),
      ),
    );
    const queryClient = renderPanel([lote(7)]);
    const invalidar = vi.spyOn(queryClient, "invalidateQueries");

    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: "Publicar convocatoria" }),
    );
    await user.click(screen.getByRole("button", { name: "Sí, publicar" }));
    await screen.findByText("Convocatoria N.º 1 publicada");

    await waitFor(() => {
      expect(invalidar).toHaveBeenCalledWith({ queryKey: ["emergencias"] });
    });
    expect(invalidar).toHaveBeenCalledWith({ queryKey: ["convocatorias"] });
  });
});
