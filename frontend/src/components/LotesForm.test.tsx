import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import type { EstadoLote, Lote } from "../schemas/lote";
import { LotesForm } from "./LotesForm";

const API_URL = "http://localhost:8000/api/v1";
const CSRF_TOKEN = "csrf-firmado";
const URL_LOTES = `${API_URL}/emergencias/31/lotes`;

function loteGuardado(
  id: number,
  tipo: string,
  cantidad: string,
  unidad: string,
  estado: EstadoLote = "BORRADOR",
): Lote {
  return {
    id,
    emergencia_id: 31,
    creado_por_usuario_id: 2,
    tipo_necesidad: tipo,
    descripcion: null,
    cantidad_requerida: cantidad,
    unidad,
    estado,
    version: 1,
    creado_en: "2026-09-19T18:20:39.102766Z",
    actualizado_en: "2026-09-19T18:20:39.102766Z",
  };
}

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderForm(lotes: Lote[] = []): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <LotesForm emergenciaId={31} csrfToken={CSRF_TOKEN} lotes={lotes} />
    </QueryClientProvider>,
  );
}

function campo(label: string, indice: number): HTMLElement {
  const elemento = screen.getAllByLabelText(label)[indice];
  if (elemento === undefined) {
    throw new Error(`No existe el campo "${label}" del lote ${indice + 1}.`);
  }
  return elemento;
}

async function completarLote(
  user: UserEvent,
  indice: number,
  tipo: string,
  cantidad: string,
  unidad: string,
): Promise<void> {
  await user.type(campo("Tipo de necesidad", indice), tipo);
  await user.type(campo("Cantidad requerida", indice), cantidad);
  await user.type(campo("Unidad", indice), unidad);
}

describe("LotesForm", () => {
  it("valida campos obligatorios y cantidades positivas", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.type(screen.getByLabelText("Cantidad requerida"), "0");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    expect(
      await screen.findByText("Ingresá el tipo de necesidad."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("La cantidad debe ser mayor a cero."),
    ).toBeInTheDocument();
    expect(screen.getByText("Ingresá la unidad.")).toBeInTheDocument();
    expect(screen.getByLabelText("Cantidad requerida")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("agrega y quita lotes sin guardar", async () => {
    const user = userEvent.setup();
    renderForm();

    expect(
      screen.queryByRole("button", { name: "Quitar lote 1" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Agregar lote" }));
    expect(screen.getAllByLabelText("Tipo de necesidad")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Quitar lote 2" }));
    expect(screen.getAllByLabelText("Tipo de necesidad")).toHaveLength(1);
  });

  it("guarda varios lotes en borrador sin publicar la convocatoria", async () => {
    let requestCredentials: RequestCredentials | undefined;
    let csrfHeader: string | null = null;
    let cuerpo: unknown;
    const publicaciones: string[] = [];
    server.use(
      http.post(URL_LOTES, async ({ request }) => {
        requestCredentials = request.credentials;
        csrfHeader = request.headers.get("X-CSRF-Token");
        cuerpo = await request.json();
        return HttpResponse.json(
          [
            loteGuardado(7, "Agua potable", "500.000", "litros"),
            loteGuardado(8, "Colchones", "40.000", "unidades"),
          ],
          { status: 201 },
        );
      }),
      http.post(`${API_URL}/emergencias/31/publicar`, ({ request }) => {
        publicaciones.push(request.url);
        return HttpResponse.json({}, { status: 200 });
      }),
    );
    const user = userEvent.setup();
    renderForm();

    await completarLote(user, 0, "Agua potable", "500", "litros");
    await user.click(screen.getByRole("button", { name: "Agregar lote" }));
    await completarLote(user, 1, "Colchones", "40", "unidades");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "2 lotes guardados en borrador.",
    );
    expect(requestCredentials).toBe("include");
    expect(csrfHeader).toBe(CSRF_TOKEN);
    expect(cuerpo).toEqual({
      lotes: [
        {
          tipo_necesidad: "Agua potable",
          cantidad_requerida: "500",
          unidad: "litros",
          descripcion: null,
        },
        {
          tipo_necesidad: "Colchones",
          cantidad_requerida: "40",
          unidad: "unidades",
          descripcion: null,
        },
      ],
    });
    expect(publicaciones).toHaveLength(0);
    expect(screen.getAllByText("Borrador")).toHaveLength(2);
  });

  it("reenvía los lotes guardados con su id para editarlos", async () => {
    const cuerpos: unknown[] = [];
    server.use(
      http.post(URL_LOTES, async ({ request }) => {
        cuerpos.push(await request.json());
        return HttpResponse.json(
          [loteGuardado(7, "Agua potable", "750.000", "litros")],
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderForm();

    await completarLote(user, 0, "Agua potable", "500", "litros");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));
    await screen.findByRole("status");

    const cantidad = screen.getByLabelText("Cantidad requerida");
    await user.clear(cantidad);
    await user.type(cantidad, "750");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    await waitFor(() => {
      expect(cuerpos).toHaveLength(2);
    });
    expect(cuerpos[1]).toEqual({
      lotes: [
        {
          id: 7,
          tipo_necesidad: "Agua potable",
          cantidad_requerida: "750",
          unidad: "litros",
          descripcion: null,
        },
      ],
    });
    expect(
      screen.queryByRole("button", { name: "Quitar lote 1" }),
    ).not.toBeInTheDocument();
  });

  it("precarga los borradores guardados y los edita por id", async () => {
    let cuerpo: unknown;
    server.use(
      http.post(URL_LOTES, async ({ request }) => {
        cuerpo = await request.json();
        return HttpResponse.json(
          [
            loteGuardado(7, "Agua potable", "900.000", "litros"),
            loteGuardado(9, "Pañales", "30", "paquetes"),
          ],
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderForm([loteGuardado(7, "Agua potable", "500.000", "litros")]);

    expect(screen.getByLabelText("Tipo de necesidad")).toHaveValue(
      "Agua potable",
    );
    expect(screen.getByLabelText("Cantidad requerida")).toHaveValue("500.000");
    expect(screen.getByText("Borrador")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Sin cambios para guardar" }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Quitar lote 1" }),
    ).not.toBeInTheDocument();

    const cantidad = screen.getByLabelText("Cantidad requerida");
    await user.clear(cantidad);
    await user.type(cantidad, "900");
    await user.click(screen.getByRole("button", { name: "Agregar lote" }));
    await completarLote(user, 1, "Pañales", "30", "paquetes");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "2 lotes guardados en borrador.",
    );
    expect(cuerpo).toEqual({
      lotes: [
        {
          id: 7,
          tipo_necesidad: "Agua potable",
          cantidad_requerida: "900",
          unidad: "litros",
          descripcion: null,
        },
        {
          tipo_necesidad: "Pañales",
          cantidad_requerida: "30",
          unidad: "paquetes",
          descripcion: null,
        },
      ],
    });
  });

  it("muestra los lotes publicados sin permitir editarlos ni reenviarlos", async () => {
    let cuerpo: unknown;
    server.use(
      http.post(URL_LOTES, async ({ request }) => {
        cuerpo = await request.json();
        return HttpResponse.json(
          [loteGuardado(8, "Abrigo", "100", "mantas")],
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderForm([
      loteGuardado(5, "Colchones", "40.000", "unidades", "PUBLICADO"),
    ]);

    const publicados = screen.getByRole("region", { name: "Lotes ya publicados" });
    expect(publicados).toHaveTextContent("Colchones");
    expect(publicados).toHaveTextContent("40.000 unidades");
    expect(publicados).toHaveTextContent("Publicado");
    expect(screen.getByLabelText("Tipo de necesidad")).toHaveValue("");

    await completarLote(user, 0, "Abrigo", "100", "mantas");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    await screen.findByText("1 lote guardado en borrador.");
    expect(cuerpo).toEqual({
      lotes: [
        {
          tipo_necesidad: "Abrigo",
          cantidad_requerida: "100",
          unidad: "mantas",
          descripcion: null,
        },
      ],
    });
  });

  it("muestra el error accionable del backend", async () => {
    server.use(
      http.post(URL_LOTES, () =>
        HttpResponse.json(
          { detail: "Solo el centro coordinador asignado gestiona estos lotes." },
          { status: 403 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderForm();

    await completarLote(user, 0, "Agua potable", "500", "litros");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Solo el centro coordinador asignado gestiona estos lotes.",
    );
  });

  it("indica la carga mientras guarda", async () => {
    let resolver: ((valor: Response) => void) | undefined;
    const pendiente = new Promise<Response>((resolve) => {
      resolver = resolve;
    });
    server.use(http.post(URL_LOTES, () => pendiente));
    const user = userEvent.setup();
    renderForm();

    await completarLote(user, 0, "Agua potable", "500", "litros");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    expect(
      await screen.findByRole("button", { name: "Guardando…" }),
    ).toBeDisabled();

    resolver?.(
      new Response(
        JSON.stringify([loteGuardado(7, "Agua potable", "500.000", "litros")]),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );

    await waitFor(() => {
      expect(screen.getByRole("status")).toBeInTheDocument();
    });
  });
});
