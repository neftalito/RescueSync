import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { EmergenciaForm } from "./EmergenciaForm";

const API_URL = "http://localhost:8000/api/v1";
const CSRF_TOKEN = "csrf-firmado";

const emergenciaCreada = {
  id: 31,
  municipio_id: 1,
  centro_coordinador_id: null,
  creada_por_usuario_id: 1,
  gravedad: "ALTA",
  zona: "NORTE",
  prioridad: 5,
  descripcion: "Inundación con familias evacuadas",
  estado: "REGISTRADA",
  bonita_sync: "PENDIENTE",
  bonita_process_instance_id: null,
  creada_en: "2026-09-19T18:20:39.102766Z",
  actualizada_en: "2026-09-19T18:20:39.102766Z",
};

const server = setupServer(
  http.post(`${API_URL}/emergencias/prioridad`, () =>
    HttpResponse.json({ prioridad: 5, comprobante: "comprobante-firmado" }),
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderForm(): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <EmergenciaForm csrfToken={CSRF_TOKEN} />
    </QueryClientProvider>,
  );
}

async function consultar(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.click(screen.getByRole("button", { name: "Consultar prioridad" }));
  expect(await screen.findByText("Prioridad 5 de 10")).toBeInTheDocument();
}

describe("EmergenciaForm", () => {
  it("presenta labels accesibles y valida sin duplicar estado", async () => {
    const user = userEvent.setup();
    renderForm();

    expect(screen.getByLabelText("Gravedad")).toBeInTheDocument();
    expect(screen.getByLabelText("Zona afectada")).toBeInTheDocument();
    expect(screen.getByLabelText("Descripción inicial")).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "Registrar emergencia" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Consultar prioridad" }));
    expect(await screen.findByText("Elegí la zona afectada.")).toBeInTheDocument();
    expect(screen.getByLabelText("Zona afectada")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("registra con el cliente centralizado y muestra el éxito", async () => {
    let requestCredentials: RequestCredentials | undefined;
    let csrfHeader: string | null = null;
    let cuerpo: unknown;
    let cuerpoConsulta: unknown;
    server.use(
      http.post(`${API_URL}/emergencias/prioridad`, async ({ request }) => {
        cuerpoConsulta = await request.json();
        return HttpResponse.json({ prioridad: 5, comprobante: "comprobante-firmado" });
      }),
      http.post(`${API_URL}/emergencias`, async ({ request }) => {
        requestCredentials = request.credentials;
        csrfHeader = request.headers.get("X-CSRF-Token");
        cuerpo = await request.json();
        return HttpResponse.json(emergenciaCreada, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderForm();

    await user.selectOptions(screen.getByLabelText("Gravedad"), "ALTA");
    await user.selectOptions(screen.getByLabelText("Zona afectada"), "NORTE");
    await consultar(user);
    await user.type(
      screen.getByLabelText("Descripción inicial"),
      "Inundación con familias evacuadas",
    );
    await user.click(
      screen.getByRole("button", { name: "Registrar emergencia" }),
    );

    expect(await screen.findByText(
      "Emergencia 31 registrada en estado REGISTRADA.",
    )).toBeInTheDocument();
    expect(requestCredentials).toBe("include");
    expect(csrfHeader).toBe(CSRF_TOKEN);
    expect(cuerpoConsulta).toEqual({ gravedad: "ALTA", zona: "NORTE" });
    expect(cuerpo).toEqual({
      gravedad: "ALTA",
      zona: "NORTE",
      descripcion: "Inundación con familias evacuadas",
      comprobante_prioridad: "comprobante-firmado",
    });
  });

  it("muestra el error accionable del backend", async () => {
    server.use(
      http.post(`${API_URL}/emergencias`, () =>
        HttpResponse.json(
          { detail: "Solo un municipio activo puede registrar emergencias." },
          { status: 403 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderForm();

    await user.selectOptions(screen.getByLabelText("Gravedad"), "MEDIA");
    await user.selectOptions(screen.getByLabelText("Zona afectada"), "NORTE");
    await consultar(user);
    await user.type(
      screen.getByLabelText("Descripción inicial"),
      "Desborde preventivo",
    );
    await user.click(
      screen.getByRole("button", { name: "Registrar emergencia" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Solo un municipio activo puede registrar emergencias.",
    );
  });

  it("indica la carga mientras registra", async () => {
    let resolver: ((valor: Response) => void) | undefined;
    const pendiente = new Promise<Response>((resolve) => {
      resolver = resolve;
    });
    server.use(http.post(`${API_URL}/emergencias`, () => pendiente));
    const user = userEvent.setup();
    renderForm();

    await user.selectOptions(screen.getByLabelText("Gravedad"), "BAJA");
    await user.selectOptions(screen.getByLabelText("Zona afectada"), "SUR");
    await consultar(user);
    await user.type(
      screen.getByLabelText("Descripción inicial"),
      "Monitoreo preventivo",
    );
    await user.click(
      screen.getByRole("button", { name: "Registrar emergencia" }),
    );

    expect(
      await screen.findByRole("button", { name: "Registrando…" }),
    ).toBeDisabled();

    resolver?.(
      new Response(JSON.stringify({ ...emergenciaCreada, id: 32 }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await waitFor(() => {
      expect(screen.getByText(/Emergencia 32 registrada/)).toBeInTheDocument();
    });
  });

  it("permite registrar otra emergencia tras el éxito", async () => {
    server.use(
      http.post(`${API_URL}/emergencias`, () =>
        HttpResponse.json(emergenciaCreada, { status: 201 }),
      ),
    );
    const user = userEvent.setup();
    renderForm();

    await user.selectOptions(screen.getByLabelText("Gravedad"), "ALTA");
    await user.selectOptions(screen.getByLabelText("Zona afectada"), "NORTE");
    await consultar(user);
    await user.type(
      screen.getByLabelText("Descripción inicial"),
      "Inundación con familias evacuadas",
    );
    await user.click(
      screen.getByRole("button", { name: "Registrar emergencia" }),
    );
    await screen.findByText(/Emergencia 31 registrada/);

    await user.click(
      screen.getByRole("button", { name: "Registrar otra emergencia" }),
    );

    expect(screen.getByLabelText("Zona afectada")).toHaveValue("");
    expect(
      screen.getByRole("button", { name: "Registrar emergencia" }),
    ).toBeDisabled();
  });

  it.each([
    ["Gravedad", "ALTA"],
    ["Zona afectada", "SUR"],
  ])("exige una nueva consulta al cambiar %s", async (campo, valor) => {
    const user = userEvent.setup();
    renderForm();

    await user.selectOptions(screen.getByLabelText("Zona afectada"), "NORTE");
    await consultar(user);
    expect(screen.getByRole("button", { name: "Registrar emergencia" })).toBeEnabled();

    await user.selectOptions(screen.getByLabelText(campo), valor);
    expect(screen.queryByText("Prioridad 5 de 10")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Registrar emergencia" })).toBeDisabled();
  });

  it("permite reintentar cuando el servicio de prioridad está caído", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${API_URL}/emergencias/prioridad`, () =>
        HttpResponse.json({ detail: "El servicio está temporalmente caído." }, {
          status: 503,
        }),
      ),
    );
    renderForm();

    await user.selectOptions(screen.getByLabelText("Zona afectada"), "NORTE");
    await user.click(screen.getByRole("button", { name: "Consultar prioridad" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("temporalmente caído");
    expect(screen.getByRole("button", { name: "Registrar emergencia" })).toBeDisabled();

    server.resetHandlers();
    await consultar(user);
  });

  it("vuelve a pedir la prioridad cuando el comprobante vence", async () => {
    const user = userEvent.setup();
    const mensaje = "Consultá la prioridad para esta gravedad y zona antes de registrar.";
    server.use(
      http.post(`${API_URL}/emergencias`, () =>
        HttpResponse.json({ detail: mensaje }, { status: 409 }),
      ),
    );
    renderForm();

    await user.selectOptions(screen.getByLabelText("Zona afectada"), "CENTRO");
    await consultar(user);
    await user.type(screen.getByLabelText("Descripción inicial"), "Inundación");
    await user.click(screen.getByRole("button", { name: "Registrar emergencia" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(mensaje);
    expect(screen.getByRole("button", { name: "Registrar emergencia" })).toBeDisabled();
    expect(screen.getByLabelText("Descripción inicial")).toHaveValue("Inundación");
    await consultar(user);
  });
});
