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
    const confirmar = screen.getByRole("button", { name: "Confirmar mis aportes al consorcio" });
    expect(confirmar).toBeDisabled();
    expect(confirmar).toHaveAccessibleDescription(/convocatoria.*abierta/i);
    const desarmar = screen.getByRole("button", { name: "Rechazar o desarmar consorcio" });
    expect(desarmar).toBeDisabled();
    expect(desarmar).toHaveAccessibleDescription(/convocatoria.*abierta/i);
});

function individual(cambios: Partial<Oferta> = {}): Oferta {
    return { ...propuesta(), ong_creadora_id: 5, estado: "PRESENTADA", editable: true,
        consorcio_editable: false, presentada_en: "2026-10-14T12:00:00Z",
        participantes: [{ ong_id: 5, nombre: "Mi ONG", rol: "LIDER", confirmada: true }],
        ...cambios };
}

it("explica que mi ONG ya confirmó sin ocultar la acción", () => {
    const oferta = propuesta();
    mostrar({ ...oferta, participantes: oferta.participantes?.map((p) => ({ ...p, confirmada: true })) });
    const confirmar = screen.getByRole("button", { name: "Confirmar mis aportes al consorcio" });
    expect(confirmar).toBeDisabled();
    expect(confirmar).toHaveAccessibleDescription(/ya confirmó/i);
    expect(screen.getByRole("button", { name: "Rechazar o desarmar consorcio" })).toBeEnabled();
});

it("explica la falta de recursos nacionales sin permitir invitaciones ni consultar candidatas", async () => {
    let consultas = 0;
    server.use(http.get(`${API}/ofertas/ongs-disponibles`, () => {
        consultas += 1;
        return HttpResponse.json([]);
    }));
    mostrar(individual({ requiere_desglose_nacional: false }));
    expect(screen.getByRole("heading", { name: "Oferta conjunta" })).toBeVisible();
    const invitar = screen.getByRole("button", { name: "Invitar ONGs" });
    expect(invitar).toBeDisabled();
    expect(invitar).toHaveAccessibleDescription(/recursos del inventario nacional/i);
    await userEvent.setup().click(invitar);
    expect(consultas).toBe(0);
});

it("explica el plazo cuando la oferta individual ya no admite invitaciones", () => {
    mostrar(individual({ editable: false }));
    const invitar = screen.getByRole("button", { name: "Invitar ONGs" });
    expect(invitar).toBeDisabled();
    expect(invitar).toHaveAccessibleDescription(/convocatoria.*abierta/i);
});

it("explica el estado de una oferta adjudicada sin ocultar las acciones del consorcio", () => {
    mostrar({ ...propuesta(), estado: "ADJUDICADA", consorcio_editable: false });
    const desarmar = screen.getByRole("button", { name: "Rechazar o desarmar consorcio" });
    expect(desarmar).toBeDisabled();
    expect(desarmar).toHaveAccessibleDescription(/adjudicada/i);
});

it("invita varias ONGs y envía únicamente la selección vigente con versión y CSRF", async () => {
    let recibido: unknown;
    let csrf: string | null = null;
    let convocatoria: string | null = null;
    server.use(
        http.get(`${API}/ofertas/ongs-disponibles`, ({ request }) => {
            convocatoria = new URL(request.url).searchParams.get("convocatoria_id");
            return HttpResponse.json([
                { ong_id: 6, nombre: "Agua solidaria" },
                { ong_id: 7, nombre: "Manos unidas" },
                { ong_id: 8, nombre: "Red de ayuda" },
            ]);
        }),
        http.post(`${API}/ofertas/9/consorcio`, async ({ request }) => {
            recibido = await request.json();
            csrf = request.headers.get("X-CSRF-Token");
            return HttpResponse.json(propuesta());
        }),
    );
    mostrar(individual());
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Invitar ONGs" }));
    const agua = await screen.findByRole("checkbox", { name: "Agua solidaria" });
    const enviar = screen.getByRole("button", { name: "Enviar propuesta de consorcio" });
    expect(enviar).toBeDisabled();
    await user.click(agua);
    await user.click(screen.getByRole("checkbox", { name: "Manos unidas" }));
    await user.click(screen.getByRole("checkbox", { name: "Red de ayuda" }));
    await user.click(screen.getByRole("checkbox", { name: "Manos unidas" }));
    await user.click(enviar);
    expect(await screen.findByText("Propuesta actualizada.")).toBeInTheDocument();
    expect(recibido).toEqual({ version_bloqueo: 2, ong_ids: [6, 8] });
    expect(csrf).toBe("csrf-local");
    expect(convocatoria).toBe("5");
});

it("permite diez invitadas y deja reemplazar una selección al alcanzar el máximo", async () => {
    server.use(http.get(`${API}/ofertas/ongs-disponibles`, () => HttpResponse.json(
        Array.from({ length: 11 }, (_, i) => ({ ong_id: i + 10, nombre: `ONG ${i + 1}` })),
    )));
    mostrar(individual());
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Invitar ONGs" }));
    await screen.findByRole("checkbox", { name: "ONG 1" });
    for (let i = 1; i <= 10; i += 1) {
        await user.click(screen.getByRole("checkbox", { name: `ONG ${i}` }));
    }
    const adicional = screen.getByRole("checkbox", { name: "ONG 11" });
    expect(adicional).toBeDisabled();
    expect(screen.getByText(/10 de 10 ONGs seleccionadas/)).toBeVisible();
    await user.click(screen.getByRole("checkbox", { name: "ONG 1" }));
    expect(adicional).toBeEnabled();
    await user.click(adicional);
    expect(adicional).toBeChecked();
});

it("explica cuando no hay candidatas y mantiene el envío deshabilitado", async () => {
    server.use(http.get(`${API}/ofertas/ongs-disponibles`, () => HttpResponse.json([])));
    mostrar(individual());
    await userEvent.setup().click(screen.getByRole("button", { name: "Invitar ONGs" }));
    expect(await screen.findByText(/No hay otras ofertas individuales/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Enviar propuesta de consorcio" })).toBeDisabled();
});
