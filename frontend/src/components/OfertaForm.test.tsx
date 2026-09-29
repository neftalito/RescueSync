import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import { OfertaForm } from "./OfertaForm";

const API_URL = "http://localhost:8000/api/v1";
const CSRF_TOKEN = "csrf-firmado";

const convocatorias = [
  {
    id: 8,
    numero: 2,
    emergencia_id: 31,
    estado: "ABIERTA",
    publicada_en: "2026-09-28T12:00:00Z",
    cierra_en: "2026-09-29T12:00:00Z",
    emergencia: {
      gravedad: "ALTA",
      zona: "Ribera norte",
      descripcion: "Inundación con familias evacuadas",
    },
    lotes: [
      {
        lote_id: 54,
        tipo_necesidad: "Agua potable",
        descripcion: "Agua para familias evacuadas",
        cantidad_publicada: "1000.000",
        unidad_publicada: "litros",
      },
      {
        lote_id: 55,
        tipo_necesidad: "Paramédicos",
        descripcion: null,
        cantidad_publicada: "10.000",
        unidad_publicada: "personas",
      },
    ],
  },
];

const ofertaCreada = {
  id: 92,
  convocatoria_id: 8,
  emergencia_id: 31,
  ong_creadora_id: 5,
  creada_por_usuario_id: 7,
  estado: "PRESENTADA",
  version_actual: 1,
  observaciones: "Entrega dentro de 24 horas",
  presentada_en: "2026-09-28T12:00:00Z",
  creada_en: "2026-09-28T12:00:00Z",
  items: [
    {
      id: 111,
      lote_id: 54,
      tipo: "RECURSO",
      descripcion: "Agua potable",
      cantidad_ofrecida: "250.500",
      unidad: "litros",
    },
    {
      id: 112,
      lote_id: 55,
      tipo: "PERSONAL",
      descripcion: "Paramédicos",
      cantidad_ofrecida: "3.000",
      unidad: "personas",
    },
  ],
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
      <OfertaForm csrfToken={CSRF_TOKEN} />
    </QueryClientProvider>,
  );
}

async function agregarLote(
  user: ReturnType<typeof userEvent.setup>,
  id: string,
): Promise<void> {
  await user.selectOptions(screen.getByLabelText("Lote para agregar"), id);
  await user.click(screen.getByRole("button", { name: "Agregar lote" }));
}

describe("OfertaForm", () => {
  it("presenta una oferta parcial con recursos y personal para varios lotes", async () => {
    let cuerpo: unknown;
    let csrfHeader: string | null = null;
    let cantidadConsultas = 0;
    server.use(
      http.get(`${API_URL}/convocatorias`, () => {
        cantidadConsultas += 1;
        return HttpResponse.json(
          cantidadConsultas === 1 ? convocatorias : [],
        );
      }),
      http.post(`${API_URL}/ofertas`, async ({ request }) => {
        csrfHeader = request.headers.get("X-CSRF-Token");
        cuerpo = await request.json();
        return HttpResponse.json(ofertaCreada, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderForm();

    await user.selectOptions(
      await screen.findByLabelText("Convocatoria"),
      "8",
    );
    await user.click(screen.getByRole("button", { name: "Presentar oferta" }));
    expect(
      await screen.findByText("Agregá al menos un lote."),
    ).toBeInTheDocument();

    await agregarLote(user, "54");
    await agregarLote(user, "55");
    const [cantidadAgua, cantidadPersonal] =
      screen.getAllByLabelText("Cantidad ofrecida");
    const [, tipoPersonal] = screen.getAllByLabelText("Tipo de aporte");
    if (
      cantidadAgua === undefined ||
      cantidadPersonal === undefined ||
      tipoPersonal === undefined
    ) {
      throw new Error("No se renderizaron los dos lotes de la oferta.");
    }
    await user.type(cantidadAgua, "250,5");
    await user.type(cantidadPersonal, "3");
    await user.selectOptions(tipoPersonal, "PERSONAL");
    await user.type(
      screen.getByLabelText("Observaciones (opcional)"),
      "Entrega dentro de 24 horas",
    );
    await user.click(screen.getByRole("button", { name: "Presentar oferta" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Oferta 92 presentada correctamente.",
    );
    expect(csrfHeader).toBe(CSRF_TOKEN);
    expect(cuerpo).toEqual({
      convocatoria_id: 8,
      observaciones: "Entrega dentro de 24 horas",
      items: [
        {
          lote_id: 54,
          tipo: "RECURSO",
          descripcion: "Agua potable",
          cantidad_ofrecida: "250.5",
          unidad: "litros",
        },
        {
          lote_id: 55,
          tipo: "PERSONAL",
          descripcion: "Paramédicos",
          cantidad_ofrecida: "3",
          unidad: "personas",
        },
      ],
    });
    await waitFor(() => expect(cantidadConsultas).toBe(2));
  });

  it("valida de forma accesible que la cantidad sea positiva", async () => {
    server.use(
      http.get(`${API_URL}/convocatorias`, () =>
        HttpResponse.json(convocatorias),
      ),
    );
    const user = userEvent.setup();
    renderForm();

    await user.selectOptions(
      await screen.findByLabelText("Convocatoria"),
      "8",
    );
    await agregarLote(user, "54");
    await user.type(screen.getByLabelText("Cantidad ofrecida"), "0");
    await user.click(screen.getByRole("button", { name: "Presentar oferta" }));

    expect(
      await screen.findByText("La cantidad ofrecida debe ser mayor que cero."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Cantidad ofrecida")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("muestra estados accesibles de carga, error y lista vacía", async () => {
    let resolver: ((response: Response) => void) | undefined;
    const pendiente = new Promise<Response>((resolve) => {
      resolver = resolve;
    });
    server.use(http.get(`${API_URL}/convocatorias`, () => pendiente));
    renderForm();

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Cargando convocatorias disponibles…",
    );
    resolver?.(HttpResponse.json([]));
    expect(
      await screen.findByText(
        "En este momento no hay convocatorias abiertas para ofertar.",
      ),
    ).toBeInTheDocument();

    cleanup();
    server.use(
      http.get(`${API_URL}/convocatorias`, () =>
        HttpResponse.json({ detail: "No hay conexión." }, { status: 503 }),
      ),
    );
    renderForm();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No hay conexión.",
    );
  });
});
