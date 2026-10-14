import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, expect, it } from "vitest";
import { ConsorcioOferta } from "./ConsorcioOferta";
import { ofertaSchema, type Oferta } from "../schemas/oferta";
const API = "http://localhost:8000/api/v1";
const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => { cleanup(); server.resetHandlers(); });
afterAll(() => server.close());
function propuesta(): Oferta {
    return ofertaSchema.parse({ id: 9, convocatoria_id: 5, emergencia_id: 31, ong_creadora_id: 4, creada_por_usuario_id: 7, estado: "BORRADOR", version_actual: 2, version_bloqueo: 2, editable: false, consorcio_editable: true, observaciones: null, presentada_en: null, creada_en: "2026-10-14T12:00:00Z", items: [], requiere_desglose_nacional: true,
        emergencia: { zona: "Ribera", gravedad: "ALTA", descripcion: "Inundación" },
        participantes: [{ ong_id: 4, nombre: "ONG líder", rol: "LIDER", confirmada: true }, { ong_id: 5, nombre: "Mi ONG", rol: "MIEMBRO", confirmada: false }] });
}
function mostrar(oferta: Oferta): void {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    client.setQueryData(["session"], { usuario: { id: 8, email: "ong@example.test", rol: "REPRESENTANTE_ONG", organizacion: { id: 5, nombre: "Mi ONG", tipo: "ONG" }, requiere_cambio_password: false }, csrf_token: "csrf-local" });
    render(<QueryClientProvider client={client}><ConsorcioOferta oferta={oferta}/></QueryClientProvider>);
}
it("confirma la versión visible con el CSRF local y conserva la identidad de cada ONG", async () => {
    let recibido: unknown;
    let csrf: string | null = null;
    const oferta = propuesta();
    server.use(http.post(`${API}/ofertas/9/consorcio/confirmacion`, async ({ request }) => {
        recibido = await request.json();
        csrf = request.headers.get("X-CSRF-Token");
        return HttpResponse.json({ ...oferta, estado: "PRESENTADA", presentada_en: "2026-10-14T12:05:00Z" });
    }));
    mostrar(oferta);
    expect(screen.getByText(/ONG líder · Líder · Confirmada/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("button", { name: "Confirmar mis aportes al consorcio" }));
    expect(await screen.findByText("Propuesta actualizada.")).toBeInTheDocument();
    expect(recibido).toEqual({ version_bloqueo: 2 });
    expect(csrf).toBe("csrf-local");
});
it("explica el rechazo de una propuesta desactualizada", async () => {
    server.use(http.post(`${API}/ofertas/9/consorcio/confirmacion`, () => HttpResponse.json({ detail: "Una oferta individual cambió. Creen otra propuesta." }, { status: 409 })));
    mostrar(propuesta());
    await userEvent.setup().click(screen.getByRole("button", { name: "Confirmar mis aportes al consorcio" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Una oferta individual cambió.");
});
it("conserva el detalle cuando la convocatoria ya no permite cambios", () => {
    mostrar({ ...propuesta(), consorcio_editable: false });
    expect(screen.getByText(/Mi ONG · Integrante/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Confirmar mis aportes al consorcio" })).not.toBeInTheDocument();
});
