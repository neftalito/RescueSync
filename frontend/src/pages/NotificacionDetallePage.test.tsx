import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { casosDetalle } from "../test/fixtures/detallesNotificacion";
import { NotificacionDetallePage } from "./NotificacionDetallePage";

const base = "http://localhost:8000/api/v1/notificaciones";
const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => { cleanup(); server.resetHandlers(); });
afterAll(() => server.close());

function pagina(id: number | string): void {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[`/notificaciones/${id}`]}><Routes>
      <Route path="/notificaciones/:notificacionId" element={<NotificacionDetallePage />} />
    </Routes></MemoryRouter>
  </QueryClientProvider>);
}

describe("Detalle de notificación", () => {
  it.each(casosDetalle)("muestra $nombre y su emergencia", async ({ id, detalle }) => {
    server.use(http.get(`${base}/${id}/detalle`, () => HttpResponse.json(detalle)));
    pagina(id);
    expect(await screen.findByRole("heading", { name: "Ribera norte" })).toBeInTheDocument();
    expect(screen.getByText("Inundación con familias evacuadas")).toBeInTheDocument();
    if (detalle.clase === "OFERTA_RECIBIDA" || (detalle.clase === "CONVOCATORIA" && detalle.mi_oferta)) {
      expect(screen.getByText("Bidones de agua")).toBeInTheDocument();
      expect(screen.getByText(/Ayuda del Delta/)).toBeInTheDocument();
      expect(screen.getByText(/25,00 litros/)).toBeInTheDocument();
    } else if (detalle.clase === "TAREA_BONITA_FALLIDA") {
      expect(screen.getByRole("heading", { name: "Validar ofertas" })).toBeInTheDocument();
      expect(screen.getByText("Tarea #99")).toBeInTheDocument();
      expect(screen.getByText(/Estado al generar el aviso: Fallida/)).toBeInTheDocument();
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
    } else if (detalle.clase === "CONVOCATORIA") {
      expect(screen.getByText(detalle.convocatoria.estado === "ABIERTA"
        ? "Tu ONG todavía no presentó una oferta para esta convocatoria."
        : "Tu ONG no participó en esta convocatoria.")).toBeInTheDocument();
    }
    if (detalle.clase === "CONVOCATORIA") {
      expect(screen.getByRole("heading", { name: "Convocatoria N.º 1" })).toBeInTheDocument();
      expect(screen.getByText("100,00 litros")).toBeInTheDocument();
      expect(screen.queryByText("Convocatoria N.º 2")).not.toBeInTheDocument();
    }
  });

  it.each([403, 404])("explica un detalle no disponible (%i)", async (status) => {
    server.use(http.get(`${base}/41/detalle`, () => HttpResponse.json({ detail: "Este aviso ya no está disponible para tu usuario." }, { status })));
    pagina(41);
    expect(await screen.findByRole("alert")).toHaveTextContent("Este aviso ya no está disponible para tu usuario.");
    expect(screen.queryByRole("region", { name: "Detalle de la oferta" })).not.toBeInTheDocument();
  });

  it("permite reintentar un fallo de transporte y muestra el detalle recuperado", async () => {
    let intentos = 0;
    server.use(http.get(`${base}/41/detalle`, () => ++intentos === 1
      ? HttpResponse.error() : HttpResponse.json(casosDetalle[0]?.detalle)));
    const user = userEvent.setup();
    pagina(41);
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("heading", { name: "Ribera norte" })).toBeInTheDocument();
  });

  it("rechaza un identificador inválido sin consultar la API", () => {
    pagina("incorrecto");
    expect(screen.getByRole("alert")).toHaveTextContent("El identificador de notificación no es válido.");
  });
});
