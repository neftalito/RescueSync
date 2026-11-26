import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router";
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
  version_bloqueo: 1,
  editable: true,
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

const ofertaPropia = {
  ...ofertaCreada,
  emergencia: convocatorias[0]?.emergencia,
};

const capacidadAguaId = "00000000-0000-4000-8000-000000000101";
const inventarioAgua = ["201", "202"].map((sufijo, index) => ({
  id: `00000000-0000-4000-8000-000000000${sufijo}`,
  ongId: "00000000-0000-4000-8000-000000000301",
  capacidadId: capacidadAguaId,
  codigoInterno: `AGUA-${index + 1}`,
  nombre: `Tanque ${index + 1}`,
  capacidad: "Agua",
  unidad: "litros",
  admiteFracciones: true,
  cantidadTotal: "1000.000",
  cantidadComprometida: "0.000",
  cantidadDisponible: "1000.000",
  activo: true,
  actualizadoEn: "2026-10-14T12:00:00Z",
}));
const convocatoriasConInventario = [{
  ...convocatorias[0],
  lotes: [{ ...convocatorias[0]?.lotes[0], capacidad_nacional_id: capacidadAguaId }],
}];

const server = setupServer(
  http.get(`${API_URL}/ofertas`, () => HttpResponse.json([])),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderForm(ofertaId?: number, loteInicialId?: number): QueryClient {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <OfertaForm
          csrfToken={CSRF_TOKEN}
          ofertaId={ofertaId}
          loteInicialId={loteInicialId}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return queryClient;
}

async function agregarLote(
  user: ReturnType<typeof userEvent.setup>,
  id: string,
): Promise<void> {
  await user.selectOptions(screen.getByLabelText("Lote para agregar"), id);
  await user.click(screen.getByRole("button", { name: "Agregar lote" }));
}

describe("OfertaForm", () => {
  it("ofrece modificar la oferta existente al llegar desde un lote de su convocatoria", async () => {
    server.use(
      http.get(`${API_URL}/convocatorias`, () => HttpResponse.json(convocatorias)),
      http.get(`${API_URL}/ofertas`, () => HttpResponse.json([ofertaPropia])),
    );
    renderForm(undefined, 55);

    expect(
      await screen.findByText(/Tu ONG ya presentó una oferta para esta convocatoria/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Modificar oferta existente" }),
    ).toHaveAttribute("href", "/ofertas/92/editar");
    expect(
      screen.queryByRole("button", { name: "Presentar oferta" }),
    ).not.toBeInTheDocument();
  });

  it("informa si el lote del enlace ya no pertenece a una convocatoria abierta", async () => {
    server.use(
      http.get(`${API_URL}/convocatorias`, () => HttpResponse.json(convocatorias)),
    );
    renderForm(undefined, 999);

    expect(
      await screen.findByText(
        "El lote seleccionado ya no está disponible en una convocatoria abierta.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Volver a convocatorias" }),
    ).toHaveAttribute("href", "/convocatorias");
  });

  it("conserva los cambios del usuario al actualizar las consultas después de precargar un lote", async () => {
    server.use(
      http.get(`${API_URL}/convocatorias`, () => HttpResponse.json(convocatorias)),
    );
    const user = userEvent.setup();
    const queryClient = renderForm(undefined, 55);

    await user.type(await screen.findByLabelText("Cantidad ofrecida"), "3");
    await queryClient.invalidateQueries({ queryKey: ["convocatorias-abiertas"] });
    expect(screen.getByLabelText("Cantidad ofrecida")).toHaveValue("3");

    await user.click(screen.getByRole("button", { name: "Quitar lote" }));
    await queryClient.invalidateQueries({ queryKey: ["convocatorias-abiertas"] });
    expect(screen.queryByLabelText("Cantidad ofrecida")).not.toBeInTheDocument();
  });

  it("calcula, valida y envía el total a partir del desglose de recursos", async () => {
    const [tanque1, tanque2] = inventarioAgua;
    let cuerpo: unknown;
    server.use(
      http.get(`${API_URL}/convocatorias`, () => HttpResponse.json(convocatoriasConInventario)),
      http.get(`${API_URL}/mi-ong/recursos`, () => HttpResponse.json(inventarioAgua)),
      http.post(`${API_URL}/ofertas`, async ({ request }) => {
        cuerpo = await request.json();
        return HttpResponse.json(ofertaCreada, { status: 201 });
      }),
    );
    renderForm(undefined, 54);
    const user = userEvent.setup();

    const total = await screen.findByLabelText("Cantidad ofrecida");
    expect(total).toHaveTextContent("—");
    await user.click(screen.getByRole("button", { name: "Presentar oferta" }));
    expect(await screen.findByText("Agregá recursos de tu inventario para este lote.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Agregar recurso" }));
    await user.selectOptions(screen.getByLabelText("Recurso"), tanque1!.id);
    const primeraCantidad = screen.getByLabelText("Cantidad del recurso");
    await user.type(primeraCantidad, "1000,001");
    await user.click(screen.getByRole("button", { name: "Presentar oferta" }));
    expect(await screen.findByText("La cantidad ofrecida no puede superar 1.000,00 litros.")).toBeInTheDocument();
    expect(cuerpo).toBeUndefined();

    await user.clear(primeraCantidad);
    await user.type(primeraCantidad, "250,125");
    await user.click(screen.getByRole("button", { name: "Agregar recurso" }));
    await user.selectOptions(screen.getAllByLabelText("Recurso")[1]!, tanque2!.id);
    await user.type(screen.getAllByLabelText("Cantidad del recurso")[1]!, "0,375");
    expect(total).toHaveTextContent("250,5");

    await user.click(screen.getAllByRole("button", { name: "Quitar recurso" })[1]!);
    expect(total).toHaveTextContent("250,125");
    await user.click(screen.getByRole("button", { name: "Presentar oferta" }));
    expect(await screen.findByText(/presentada correctamente/)).toBeInTheDocument();
    expect(cuerpo).toMatchObject({ items: [{
      cantidad_ofrecida: "250.125",
      aportes: [{ recurso_nacional_id: tanque1!.id, cantidad: "250.125" }],
    }] });
  });

  it("explica que se necesita conectar la cuenta nacional para elegir recursos", async () => {
    server.use(
      http.get(`${API_URL}/convocatorias`, () => HttpResponse.json([{ ...convocatorias[0], lotes: [{ ...convocatorias[0]?.lotes[0], capacidad_nacional_id: "00000000-0000-4000-8000-000000000101" }] }])),
      http.get(`${API_URL}/mi-ong/recursos`, () => HttpResponse.json({ detail: "Conectá tu cuenta nacional." }, { status: 401 })),
    );
    renderForm();
    const user = userEvent.setup();
    await user.selectOptions(await screen.findByLabelText("Convocatoria"), "8");
    await agregarLote(user, "54");
    expect(await screen.findByRole("alert")).toHaveTextContent("Conectá tu cuenta nacional.");
    expect(screen.getByRole("link", { name: "Ir a Mis recursos" })).toHaveAttribute("href", "/mis-recursos");
  });

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
    expect(
      screen.queryByRole("button", { name: "Presentar otra oferta" }),
    ).not.toBeInTheDocument();
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

  it("rechaza una cantidad mayor que la publicada", async () => {
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
    await user.type(screen.getByLabelText("Cantidad ofrecida"), "1000,001");
    await user.click(screen.getByRole("button", { name: "Presentar oferta" }));

    expect(
      await screen.findByText(
        "La cantidad ofrecida no puede superar 1.000,00 litros.",
      ),
    ).toBeInTheDocument();
  });

  it("precarga y modifica la única oferta de la convocatoria", async () => {
    let cuerpo: unknown;
    server.use(
      http.get(`${API_URL}/convocatorias`, () =>
        HttpResponse.json(convocatorias),
      ),
      http.get(`${API_URL}/ofertas`, () => HttpResponse.json([ofertaPropia])),
      http.put(`${API_URL}/ofertas/92`, async ({ request }) => {
        cuerpo = await request.json();
        return HttpResponse.json({
          ...ofertaCreada,
          version_actual: 2,
          version_bloqueo: 2,
        });
      }),
    );
    const user = userEvent.setup();
    renderForm(92);

    expect(await screen.findByDisplayValue("250,50")).toBeInTheDocument();
    await user.clear(screen.getAllByLabelText("Cantidad ofrecida")[0]!);
    await user.type(screen.getAllByLabelText("Cantidad ofrecida")[0]!, "300");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Oferta 92 actualizada correctamente.",
    );
    expect(cuerpo).toEqual({
      version_bloqueo: 1,
      observaciones: "Entrega dentro de 24 horas",
      items: [
        {
          lote_id: 54,
          tipo: "RECURSO",
          descripcion: "Agua potable",
          cantidad_ofrecida: "300",
          unidad: "litros",
        },
        {
          lote_id: 55,
          tipo: "PERSONAL",
          descripcion: "Paramédicos",
          cantidad_ofrecida: "3.00",
          unidad: "personas",
        },
      ],
    });
  });

  it("recalcula una oferta existente al cambiar la cantidad de un recurso", async () => {
    const recurso = inventarioAgua[0]!;
    let cuerpo: unknown;
    const ofertaConInventario = {
      ...ofertaPropia,
      items: [{
        ...ofertaPropia.items[0],
        cantidad_ofrecida: "250.501",
        aportes: [{
          id: 1,
          ong_id: ofertaPropia.ong_creadora_id,
          recurso_nacional_id: recurso.id,
          capacidad_nacional_id: capacidadAguaId,
          cantidad: "250.501",
          unidad: recurso.unidad,
        }],
      }],
    };
    server.use(
      http.get(`${API_URL}/convocatorias`, () => HttpResponse.json(convocatoriasConInventario)),
      http.get(`${API_URL}/mi-ong/recursos`, () => HttpResponse.json(inventarioAgua)),
      http.get(`${API_URL}/ofertas`, () => HttpResponse.json([ofertaConInventario])),
      http.put(`${API_URL}/ofertas/92`, async ({ request }) => {
        cuerpo = await request.json();
        return HttpResponse.json({ ...ofertaConInventario, version_actual: 2 });
      }),
    );
    const user = userEvent.setup();
    renderForm(92);

    const total = await screen.findByLabelText("Cantidad ofrecida");
    expect(total).toHaveTextContent("250,501");
    const cantidad = screen.getByLabelText("Cantidad del recurso");
    await user.clear(cantidad);
    await user.type(cantidad, "251,125");
    expect(total).toHaveTextContent("251,125");
    await user.click(screen.getByRole("button", { name: "Guardar cambios" }));

    expect(await screen.findByText(/actualizada correctamente/)).toBeInTheDocument();
    expect(cuerpo).toMatchObject({ items: [{
      cantidad_ofrecida: "251.125",
      aportes: [{ recurso_nacional_id: recurso.id, cantidad: "251.125" }],
    }] });
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
        "En este momento no hay convocatorias abiertas sin una oferta de tu ONG.",
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
