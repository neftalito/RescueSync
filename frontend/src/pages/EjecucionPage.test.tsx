import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import type { Role, Session } from "../schemas/auth";
import { EjecucionPage } from "./EjecucionPage";

const base = "http://localhost:8000/api/v1/emergencias/31";
const validacionId = "00000000-0000-4000-8000-000000000101";
const participacionId = "00000000-0000-4000-8000-000000000102";
const evaluacion = {
  validacion: { validacionId, revision: 2, convocatoriaId: 7, vigente: true, lotesCompatiblesCubiertos: true,
    cobertura: [{ loteId: 1, cantidadRequerida: "6.000", cantidadAsignable: "6.000", faltante: "0.000", unidad: "personas", aportes: [{ aporteId: 20, cantidad: "6.000" }] }],
  }, permiteParcial: false, diagnosticos: [],
  aportes: [{ aporteId: 20, ofertaId: 10, version: 3, loteId: 1, ongId: 2, perfilCompetencia: null, cantidadOfrecida: "6.000", cantidadDisponible: "6.000", unidad: "personas", admiteFracciones: false }],
};
const seguimiento = { idEmergencia: 31, estado: "EN_EVALUACION", adjudicaciones: [], puedeSolicitarCierre: false, cierre: null };
const server = setupServer(
  http.get(`${base}/ofertas-validadas`, () => HttpResponse.json(evaluacion)),
  http.get(`${base}/adjudicaciones`, () => HttpResponse.json(seguimiento)),
  http.get(`${base}/comandos-bonita`, () => HttpResponse.json([])),
);
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => { cleanup(); server.resetHandlers(); });
afterAll(() => server.close());

function pagina(rol: Role): void {
  const session: Session = { usuario: { id: 1, email: "usuario@example.test", rol, requiere_cambio_password: false, organizacion: { id: 2, nombre: "Organización", tipo: rol === "REPRESENTANTE_ONG" ? "ONG" : rol === "OPERADOR_MUNICIPAL" ? "MUNICIPIO" : "CENTRO_COORDINADOR" } }, csrf_token: "csrf-firmado" };
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><MemoryRouter initialEntries={["/emergencias/31/ejecucion"]}><Routes><Route path="/emergencias/:emergenciaId/ejecucion" element={<EjecucionPage session={session} />} /></Routes></MemoryRouter></QueryClientProvider>);
}

describe("Evaluación y ejecución", () => {
  it("envía cantidades exactas y revisión vigente con CSRF", async () => {
    const usuario = userEvent.setup();
    let payload: unknown;
    let csrf: string | null = null;
    server.use(http.post(`${base}/adjudicaciones`, async ({ request }) => { payload = await request.json(); csrf = request.headers.get("X-CSRF-Token"); return HttpResponse.json({}); }));
    pagina("OPERADOR_MUNICIPAL");
    await usuario.type(await screen.findByLabelText("Cantidad aporte 20"), "6");
    await usuario.click(screen.getByRole("button", { name: "Solicitar adjudicación" }));
    await screen.findByText(/Solicitud guardada/);
    expect(payload).toMatchObject({ validacionId, revision: 2, aportes: [{ aporteId: 20, cantidad: "6" }] });
    expect(csrf).toBe("csrf-firmado");
  });

  it("muestra la cobertura con dos decimales", async () => {
    server.use(http.get(`${base}/ofertas-validadas`, () => HttpResponse.json({
      ...evaluacion,
      validacion: {
        ...evaluacion.validacion,
        lotesCompatiblesCubiertos: false,
        cobertura: [{ loteId: 1, cantidadRequerida: "5.000", cantidadAsignable: "3.000", faltante: "2.000", unidad: "personas", aportes: [] }],
      },
    })));
    pagina("COORDINADOR_REGIONAL");
    expect(await screen.findByText("Lote 1: 3,00 de 5,00 personas; faltante 2,00.")).toBeInTheDocument();
    expect(screen.queryByText(/3\.000/)).not.toBeInTheDocument();
  });

  it("muestra el perfil de la oferta con dos decimales", async () => {
    server.use(http.get(`${base}/ofertas-validadas`, () => HttpResponse.json({
      ...evaluacion,
      diagnosticos: [{
        ofertaId: 10,
        ongId: 3,
        perfilCompetencia: {
          ongId: "00000000-0000-4000-8000-000000000103",
          nombre: "Ayuda Sin Fronteras",
          estadoOng: "HABILITADA",
          evaluadoEn: "2026-11-26T19:00:00Z",
          capacidadesDeclaradas: [{
            capacidadId: "00000000-0000-4000-8000-000000000104",
            codigo: "PP", nombre: "Personal paramédico", tipo: "PERSONAL",
            unidad: "personas", admiteFracciones: false,
            cantidadTotal: "30.000", cantidadComprometida: "0.000", cantidadDisponible: "30.000",
          }],
        },
        motivos: [{ codigo: "ONGC", mensaje: "Perfil informativo." }],
      }],
    })));
    pagina("COORDINADOR_REGIONAL");
    expect(await screen.findAllByText("30,00 personas")).toHaveLength(2);
    expect(screen.getByText("0,00 personas")).toBeInTheDocument();
    expect(screen.queryByText(/30\.000|0\.000/)).not.toBeInTheDocument();
  });

  it("conserva la identidad al reintentar una respuesta perdida", async () => {
    const usuario = userEvent.setup();
    const solicitudes: unknown[] = [];
    server.use(http.post(`${base}/adjudicaciones`, async ({ request }) => { solicitudes.push(await request.json()); return solicitudes.length === 1 ? HttpResponse.error() : HttpResponse.json({}); }));
    pagina("OPERADOR_MUNICIPAL");
    await usuario.type(await screen.findByLabelText("Cantidad aporte 20"), "6");
    await usuario.click(screen.getByRole("button", { name: "Solicitar adjudicación" }));
    await screen.findByRole("alert");
    await usuario.click(screen.getByRole("button", { name: "Solicitar adjudicación" }));
    await waitFor(() => expect(solicitudes).toHaveLength(2));
    expect(solicitudes[0]).toEqual(solicitudes[1]);
  });

  it("bloquea cierre prematuro y exige motivo para una alternativa", async () => {
    const usuario = userEvent.setup();
    server.use(http.get(`${base}/ofertas-validadas`, () => HttpResponse.json({ ...evaluacion, validacion: { ...evaluacion.validacion, lotesCompatiblesCubiertos: false } })));
    pagina("COORDINADOR_REGIONAL");
    await usuario.click(await screen.findByRole("button", { name: "Reabrir convocatoria" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Explicá el motivo");
    expect(screen.getByRole("button", { name: "Solicitar cierre de emergencia" })).toBeDisabled();
  });

  it("permite corregir cantidades cuando la API rechaza el comando sin efectos", async () => {
    const usuario = userEvent.setup();
    const solicitudes: unknown[] = [];
    server.use(http.post(`${base}/adjudicaciones`, async ({ request }) => {
      solicitudes.push(await request.json());
      return solicitudes.length === 1 ? HttpResponse.json({ detail: "Revisá las cantidades." }, { status: 422 }) : HttpResponse.json({});
    }));
    pagina("OPERADOR_MUNICIPAL");
    const cantidad = await screen.findByLabelText("Cantidad aporte 20");
    await usuario.type(cantidad, "6");
    await usuario.click(screen.getByRole("button", { name: "Solicitar adjudicación" }));
    await screen.findByText("Revisá las cantidades.");
    await usuario.clear(cantidad);
    await usuario.type(cantidad, "5");
    await usuario.click(screen.getByRole("button", { name: "Solicitar adjudicación" }));
    await screen.findByText(/Solicitud guardada/);
    expect(solicitudes[1]).toMatchObject({ aportes: [{ aporteId: 20, cantidad: "5" }] });
  });

  it("muestra finalización informada como liberación pendiente", async () => {
    server.use(http.get(`${base}/adjudicaciones`, () => HttpResponse.json({ ...seguimiento, estado: "EN_EJECUCION", adjudicaciones: [{ adjudicacionId: validacionId, estado: "CONFIRMADA", estadoIntegracion: "CONFIRMADA", participantes: [{ participacionId, ongId: 2, estado: "FINALIZACION_SOLICITADA", compromisoIds: [validacionId], finalizacionId: validacionId }] }] })));
    pagina("REPRESENTANTE_ONG");
    expect(await screen.findByText(/Finalización informada; liberación pendiente/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Informar finalización" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Solicitar adjudicación" })).not.toBeInTheDocument();
  });
});
