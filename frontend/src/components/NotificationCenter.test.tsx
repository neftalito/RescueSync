import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { NotificationCenter } from "./NotificationCenter";

const API_URL = "http://localhost:8000/api/v1";
const notificacion = {
  id: 41,
  usuario_id: 7,
  tipo: "CONVOCATORIA_PUBLICADA",
  titulo: "Nueva convocatoria abierta",
  mensaje: "Se publicó una convocatoria para la emergencia de Ribera norte.",
  ruta: "/convocatorias",
  leida_en: null,
  creada_en: "2026-09-28T18:20:39.102766Z",
};

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderCenter(): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <NotificationCenter csrfToken="csrf-firmado" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NotificationCenter", () => {
  it("muestra el contador y permite leer una novedad", async () => {
    let csrf: string | null = null;
    server.use(
      http.get(`${API_URL}/notificaciones`, () =>
        HttpResponse.json([notificacion]),
      ),
      http.patch(`${API_URL}/notificaciones/41/leida`, ({ request }) => {
        csrf = request.headers.get("X-CSRF-Token");
        return HttpResponse.json({
          ...notificacion,
          leida_en: "2026-09-28T18:21:00Z",
        });
      }),
    );
    const user = userEvent.setup();
    renderCenter();

    const boton = await screen.findByRole("button", { name: /Notificaciones/ });
    await waitFor(() => expect(boton).toHaveTextContent("1"));
    await user.click(boton);
    expect(
      await screen.findByText("Nueva convocatoria abierta"),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Ver detalle" }));
    await waitFor(() => expect(csrf).toBe("csrf-firmado"));
  });

  it("marca todas las novedades como vistas desde el botón de doble tick", async () => {
    let csrf: string | null = null;
    server.use(
      http.get(`${API_URL}/notificaciones`, () =>
        HttpResponse.json([
          notificacion,
          { ...notificacion, id: 42, titulo: "Otra novedad" },
        ]),
      ),
      http.patch(`${API_URL}/notificaciones/leidas`, ({ request }) => {
        csrf = request.headers.get("X-CSRF-Token");
        return HttpResponse.json({
          cantidad_actualizada: 2,
          leida_en: "2026-09-28T18:22:00Z",
        });
      }),
    );
    const user = userEvent.setup();
    renderCenter();

    await user.click(
      await screen.findByRole("button", { name: /Notificaciones/ }),
    );
    const marcarTodas = await screen.findByRole("button", {
      name: "Marcar todas como vistas",
    });
    expect(screen.getByText("2 sin leer")).toBeInTheDocument();

    await user.click(marcarTodas);

    await waitFor(() => expect(csrf).toBe("csrf-firmado"));
    expect(screen.getByText("0 sin leer")).toBeInTheDocument();
    expect(marcarTodas).toBeDisabled();
  });

  it("contempla los estados vacío y de error", async () => {
    server.use(
      http.get(`${API_URL}/notificaciones`, () => HttpResponse.json([])),
    );
    const user = userEvent.setup();
    renderCenter();
    await user.click(
      await screen.findByRole("button", { name: "Notificaciones" }),
    );
    expect(await screen.findByText("No hay novedades todavía.")).toBeInTheDocument();

    cleanup();
    server.use(
      http.get(`${API_URL}/notificaciones`, () =>
        HttpResponse.json({ detail: "No disponible" }, { status: 503 }),
      ),
    );
    renderCenter();
    await user.click(
      await screen.findByRole("button", { name: "Notificaciones" }),
    );
    expect(
      await screen.findByText("No pudimos cargar las notificaciones."),
    ).toBeInTheDocument();
  });
});
