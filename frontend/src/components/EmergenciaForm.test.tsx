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
  zona: "Ribera norte",
  descripcion: "Inundación con familias evacuadas",
  estado: "REGISTRADA",
  bonita_sync: "PENDIENTE",
  bonita_process_instance_id: null,
  creada_en: "2026-09-19T18:20:39.102766Z",
  actualizada_en: "2026-09-19T18:20:39.102766Z",
};

const server = setupServer();

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

describe("EmergenciaForm", () => {
  it("presenta labels accesibles y valida sin duplicar estado", async () => {
    const user = userEvent.setup();
    renderForm();

    expect(screen.getByLabelText("Gravedad")).toBeInTheDocument();
    expect(screen.getByLabelText("Zona afectada")).toBeInTheDocument();
    expect(screen.getByLabelText("Descripción inicial")).toBeInTheDocument();

    await user.clear(screen.getByLabelText("Zona afectada"));
    await user.clear(screen.getByLabelText("Descripción inicial"));
    await user.click(
      screen.getByRole("button", { name: "Registrar emergencia" }),
    );

    expect(await screen.findByText("Ingresá la zona afectada.")).toBeInTheDocument();
    expect(
      screen.getByText("Ingresá una descripción inicial."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Zona afectada")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("registra con el cliente centralizado y muestra el éxito", async () => {
    let requestCredentials: RequestCredentials | undefined;
    let csrfHeader: string | null = null;
    let cuerpo: unknown;
    server.use(
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
    await user.type(screen.getByLabelText("Zona afectada"), "Ribera norte");
    await user.type(
      screen.getByLabelText("Descripción inicial"),
      "Inundación con familias evacuadas",
    );
    await user.click(
      screen.getByRole("button", { name: "Registrar emergencia" }),
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Emergencia 31 registrada en estado REGISTRADA.",
    );
    expect(requestCredentials).toBe("include");
    expect(csrfHeader).toBe(CSRF_TOKEN);
    expect(cuerpo).toEqual({
      gravedad: "ALTA",
      zona: "Ribera norte",
      descripcion: "Inundación con familias evacuadas",
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
    await user.type(screen.getByLabelText("Zona afectada"), "Ribera norte");
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
    await user.type(screen.getByLabelText("Zona afectada"), "Arroyo Sur");
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
      expect(screen.getByRole("status")).toBeInTheDocument();
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
    await user.type(screen.getByLabelText("Zona afectada"), "Ribera norte");
    await user.type(
      screen.getByLabelText("Descripción inicial"),
      "Inundación con familias evacuadas",
    );
    await user.click(
      screen.getByRole("button", { name: "Registrar emergencia" }),
    );
    await screen.findByRole("status");

    await user.click(
      screen.getByRole("button", { name: "Registrar otra emergencia" }),
    );

    expect(screen.getByLabelText("Zona afectada")).toHaveValue("");
    expect(
      screen.getByRole("button", { name: "Registrar emergencia" }),
    ).toBeInTheDocument();
  });
});
