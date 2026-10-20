import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import type { EstadoLote, Lote } from "../schemas/lote";
import { LotesForm } from "./LotesForm";

const API_URL = "http://localhost:8000/api/v1";
const CSRF_TOKEN = "csrf-firmado";
const URL_LOTES = `${API_URL}/emergencias/31/lotes`;
const URL_PUBLICAR = `${API_URL}/emergencias/31/publicar`;
const URL_CATALOGO = `${API_URL}/emergencias/catalogos/capacidades-nacionales`;
const capacidades = [
  { nombre: "Agua potable", unidad: "litros" },
  { nombre: "Colchones", unidad: "unidades" },
  { nombre: "Pañales", unidad: "paquetes" },
  { nombre: "Abrigo", unidad: "mantas" },
].map((capacidad, index) => ({
  ...capacidad,
  id: `00000000-0000-4000-8000-${String(index + 101).padStart(12, "0")}`,
  codigo: `CAPACIDAD_${index}`,
  tipo: "SUMINISTRO",
  admiteFracciones: index === 0,
}));

function capacidadId(nombre: string): string {
  const capacidad = capacidades.find((item) => item.nombre === nombre);
  if (!capacidad) throw new Error(`No existe la capacidad de prueba ${nombre}.`);
  return capacidad.id;
}

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
    capacidad_nacional_id: capacidadId(tipo === "Agua" ? "Agua potable" : tipo),
    descripcion: null,
    cantidad_requerida: cantidad,
    unidad,
    estado,
    version: 1,
    creado_en: "2026-09-19T18:20:39.102766Z",
    actualizado_en: "2026-09-19T18:20:39.102766Z",
  };
}

const server = setupServer(
  http.get(URL_CATALOGO, () => HttpResponse.json(capacidades)),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

async function renderForm(
  lotes: Lote[] = [],
  convocatoriaPublicada = false,
  esperarCatalogo = true,
): Promise<void> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <LotesForm
        emergenciaId={31}
        csrfToken={CSRF_TOKEN}
        convocatoriaPublicada={convocatoriaPublicada}
        lotes={lotes}
      />
    </QueryClientProvider>,
  );
  if (esperarCatalogo) {
    await waitFor(() => expect(screen.getAllByLabelText("Capacidad")[0]).toBeEnabled());
  }
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
  await user.selectOptions(campo("Capacidad", indice), capacidadId(tipo));
  await user.type(campo("Cantidad requerida", indice), cantidad);
  expect(campo("Unidad", indice)).toHaveValue(unidad);
  expect(campo("Unidad", indice)).toHaveAttribute("readonly");
}

describe("LotesForm", () => {
  it("muestra Cargando... en el selector hasta que se obtienen las capacidades", async () => {
    let liberarRespuesta: () => void = () => undefined;
    const respuestaPendiente = new Promise<void>((resolve) => {
      liberarRespuesta = resolve;
    });
    server.use(http.get(URL_CATALOGO, async () => {
      await respuestaPendiente;
      return HttpResponse.json(capacidades);
    }));
    await renderForm([], false, false);
    const selector = screen.getByRole("combobox", { name: "Capacidad" });

    try {
      expect(selector).toBeDisabled();
      expect(within(selector).getByRole("option", { selected: true })).toHaveTextContent("Cargando...");
    } finally {
      liberarRespuesta();
    }

    await waitFor(() => expect(selector).toBeEnabled());
    expect(within(selector).getByRole("option", { selected: true })).toHaveTextContent("Elegí una capacidad");
    expect(within(selector).queryByRole("option", { name: "Cargando..." })).not.toBeInTheDocument();
    expect(within(selector).getByRole("option", { name: "Agua potable" })).toBeInTheDocument();
  });

  it("reemplaza el tipo manual por la capacidad y guarda su nombre, unidad y riesgo", async () => {
    const capacidadId = "00000000-0000-4000-8000-000000000101";
    let cuerpo: unknown;
    server.use(
      http.get(`${API_URL}/emergencias/catalogos/capacidades-nacionales`, () => HttpResponse.json([{ id: capacidadId, codigo: "AGUA", nombre: "Agua", tipo: "SUMINISTRO", unidad: "litros", admiteFracciones: true }])),
      http.post(URL_LOTES, async ({ request }) => { cuerpo = await request.json(); return HttpResponse.json([loteGuardado(1, "Agua", "10", "litros")]); }),
    );
    await renderForm();
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Cantidad requerida"), "10");
    expect(screen.queryByLabelText("Tipo de necesidad")).not.toBeInTheDocument();
    await screen.findByRole("option", { name: "Agua" });
    await user.selectOptions(screen.getByLabelText("Capacidad"), capacidadId);
    expect(screen.getByLabelText("Unidad")).toHaveValue("litros");
    expect(screen.getByLabelText("Unidad")).toHaveAttribute("readonly");
    await user.selectOptions(screen.getByLabelText("Riesgo requerido"), "ALTA");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));
    await waitFor(() => expect(cuerpo).toMatchObject({ lotes: [{ capacidad_nacional_id: capacidadId, tipo_necesidad: "Agua", riesgo_requerido: "ALTA", unidad: "litros" }] }));
  });

  it("valida campos obligatorios y cantidades positivas", async () => {
    const user = userEvent.setup();
    await renderForm();

    await user.type(screen.getByLabelText("Cantidad requerida"), "0");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    expect(
      await screen.findByText("Seleccioná una capacidad."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("La cantidad debe ser mayor a cero."),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Cantidad requerida")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });

  it("cambia la unidad con la capacidad y conserva cantidad y descripción", async () => {
    let cuerpo: unknown;
    server.use(http.post(URL_LOTES, async ({ request }) => {
      cuerpo = await request.json();
      return HttpResponse.json([loteGuardado(1, "Abrigo", "500", "mantas")]);
    }));
    const user = userEvent.setup();
    await renderForm();
    await completarLote(user, 0, "Agua potable", "500", "litros");
    await user.type(screen.getByLabelText("Descripción (opcional)"), "Entregar en el refugio");

    await user.selectOptions(screen.getByLabelText("Capacidad"), capacidadId("Abrigo"));

    expect(screen.getByLabelText("Unidad")).toHaveValue("mantas");
    expect(screen.getByLabelText("Cantidad requerida")).toHaveValue("500");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));
    await waitFor(() => expect(cuerpo).toEqual({ lotes: [{
      capacidad_nacional_id: capacidadId("Abrigo"), tipo_necesidad: "Abrigo",
      cantidad_requerida: "500", unidad: "mantas", descripcion: "Entregar en el refugio",
    }] }));
  });

  it("borra la unidad y exige una capacidad al quitar la selección", async () => {
    const user = userEvent.setup();
    await renderForm();
    await completarLote(user, 0, "Agua potable", "500", "litros");

    await user.selectOptions(screen.getByLabelText("Capacidad"), "");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    expect(await screen.findByText("Seleccioná una capacidad.")).toBeInTheDocument();
    expect(screen.getByLabelText("Unidad")).toHaveValue("");
    expect(screen.getByLabelText("Capacidad")).toHaveAttribute("aria-invalid", "true");
  });

  it("conserva la cantidad y permite reintentar si falla el catálogo", async () => {
    let consultas = 0;
    server.use(http.get(URL_CATALOGO, () => {
      consultas += 1;
      return consultas === 1
        ? HttpResponse.json({ detail: "El catálogo nacional para coordinación no está configurado." }, { status: 503 })
        : HttpResponse.json(capacidades);
    }));
    const user = userEvent.setup();
    await renderForm([], false, false);
    expect(await screen.findByRole("alert")).toHaveTextContent("El catálogo nacional para coordinación no está configurado.");
    expect(screen.getByLabelText("Capacidad")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Guardar borrador" })).toBeDisabled();
    await user.type(screen.getByLabelText("Cantidad requerida"), "500");

    await user.click(screen.getByRole("button", { name: "Reintentar catálogo" }));
    await screen.findByRole("option", { name: "Agua potable" });

    expect(screen.getByLabelText("Capacidad")).toBeEnabled();
    expect(screen.getByLabelText("Cantidad requerida")).toHaveValue("500");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(consultas).toBe(2);
  });

  it("explica que no hay capacidades activas y bloquea guardar", async () => {
    server.use(http.get(URL_CATALOGO, () => HttpResponse.json([])));
    await renderForm([], false, false);

    expect(await screen.findByText("El catálogo nacional todavía no tiene capacidades activas.")).toBeInTheDocument();
    expect(screen.getByLabelText("Capacidad")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Guardar borrador" })).toBeDisabled();
  });

  it("requiere elegir una capacidad para actualizar un borrador anterior sin vínculo", async () => {
    let cuerpo: unknown;
    server.use(http.post(URL_LOTES, async ({ request }) => {
      cuerpo = await request.json();
      return HttpResponse.json([loteGuardado(7, "Agua potable", "750", "litros")]);
    }));
    const user = userEvent.setup();
    await renderForm([{ ...loteGuardado(7, "Agua potable", "500", "litros"), capacidad_nacional_id: null }]);
    expect(screen.getByLabelText("Capacidad")).toHaveValue("");
    expect(screen.getByText(/Necesidad guardada: Agua potable/)).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Cantidad requerida"));
    await user.type(screen.getByLabelText("Cantidad requerida"), "750");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));
    expect(await screen.findByText("Seleccioná una capacidad.")).toBeInTheDocument();
    expect(cuerpo).toBeUndefined();

    await user.selectOptions(screen.getByLabelText("Capacidad"), capacidadId("Agua potable"));
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    await waitFor(() => expect(cuerpo).toMatchObject({ lotes: [{
      id: 7, version: 1, capacidad_nacional_id: capacidadId("Agua potable"),
      tipo_necesidad: "Agua potable", unidad: "litros", cantidad_requerida: "750",
    }] }));
  });

  it("pide reemplazar una capacidad guardada que ya no está disponible", async () => {
    let guardados = 0;
    server.use(
      http.get(URL_CATALOGO, () => HttpResponse.json(capacidades.slice(1))),
      http.post(URL_LOTES, () => { guardados += 1; return HttpResponse.json([]); }),
    );
    const user = userEvent.setup();
    await renderForm([loteGuardado(7, "Agua potable", "500", "litros")]);
    expect(screen.getByLabelText("Capacidad")).toHaveDisplayValue("Agua potable (no disponible)");
    await user.type(screen.getByLabelText("Descripción (opcional)"), "Entrega urgente");

    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    expect(await screen.findByText("Seleccioná una capacidad disponible en el catálogo.")).toBeInTheDocument();
    expect(guardados).toBe(0);
  });

  it("agrega y quita lotes sin guardar", async () => {
    const user = userEvent.setup();
    await renderForm();

    expect(
      screen.queryByRole("button", { name: "Quitar lote 1" }),
    ).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Agregar lote" }));
    expect(screen.getAllByLabelText("Capacidad")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Quitar lote 2" }));
    expect(screen.getAllByLabelText("Capacidad")).toHaveLength(1);
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
    await renderForm();

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
          capacidad_nacional_id: capacidadId("Agua potable"),
          tipo_necesidad: "Agua potable",
          cantidad_requerida: "500",
          unidad: "litros",
          descripcion: null,
        },
        {
          capacidad_nacional_id: capacidadId("Colchones"),
          tipo_necesidad: "Colchones",
          cantidad_requerida: "40",
          unidad: "unidades",
          descripcion: null,
        },
      ],
    });
    expect(publicaciones).toHaveLength(0);
    expect(screen.getAllByText("Borrador")).toHaveLength(2);
    expect(screen.getAllByLabelText("Cantidad requerida")[0]).toHaveValue(
      "500,00",
    );
    expect(screen.getAllByLabelText("Cantidad requerida")[1]).toHaveValue(
      "40,00",
    );
  });

  it("publica explícitamente los lotes guardados y muestra el resultado", async () => {
    let csrfHeader: string | null = null;
    server.use(
      http.post(URL_PUBLICAR, ({ request }) => {
        csrfHeader = request.headers.get("X-CSRF-Token");
        return HttpResponse.json(
          {
            id: 14,
            emergencia_id: 31,
            numero: 1,
            estado: "ABIERTA",
            publicada_en: "2026-09-28T16:00:00Z",
            cierra_en: "2026-09-29T16:00:00Z",
            lotes: [
              {
                lote_id: 7,
                tipo_necesidad: "Agua potable",
                descripcion: "Bidones",
                cantidad_publicada: "500.000",
                unidad_publicada: "litros",
              },
            ],
            bonita_generar_lotes_estado: "COMPLETADA",
            bonita_generar_lotes_ultimo_error: null,
            bonita_generar_lotes_ultimo_intento_en: "2026-09-28T16:00:01Z",
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    await renderForm([loteGuardado(7, "Agua potable", "500.000", "litros")]);

    await user.click(
      screen.getByRole("button", { name: "Publicar convocatoria" }),
    );

    expect(
      await screen.findByText("Convocatoria publicada."),
    ).toBeInTheDocument();
    expect(screen.getByText("Se incluyeron 1 lote.")).toBeInTheDocument();
    expect(csrfHeader).toBe(CSRF_TOKEN);
    expect(
      screen.getByRole("button", { name: "Convocatoria publicada" }),
    ).toBeDisabled();
  });

  it("no vuelve a publicar una convocatoria ya publicada", async () => {
    let publicaciones = 0;
    server.use(
      http.post(URL_PUBLICAR, () => {
        publicaciones += 1;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    await renderForm(
      [loteGuardado(7, "Agua potable", "500.000", "litros")],
      true,
    );

    const boton = screen.getByRole("button", {
      name: "Convocatoria publicada",
    });
    expect(boton).toBeDisabled();

    await user.click(boton);

    expect(publicaciones).toBe(0);
  });

  it("explica el rechazo al publicar sin perder los borradores", async () => {
    server.use(
      http.post(URL_PUBLICAR, () =>
        HttpResponse.json(
          { detail: "La convocatoria requiere al menos un lote válido." },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    await renderForm([loteGuardado(7, "Agua potable", "500.000", "litros")]);

    await user.click(
      screen.getByRole("button", { name: "Publicar convocatoria" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "La convocatoria requiere al menos un lote válido.",
    );
    expect(screen.getByLabelText("Capacidad")).toHaveDisplayValue(
      "Agua potable",
    );
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
    await renderForm();

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
          version: 1,
          capacidad_nacional_id: capacidadId("Agua potable"),
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
    await renderForm([loteGuardado(7, "Agua potable", "500.000", "litros")]);

    expect(screen.getByLabelText("Capacidad")).toHaveDisplayValue(
      "Agua potable",
    );
    expect(screen.getByLabelText("Cantidad requerida")).toHaveValue("500,00");
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
          version: 1,
          capacidad_nacional_id: capacidadId("Agua potable"),
          tipo_necesidad: "Agua potable",
          cantidad_requerida: "900",
          unidad: "litros",
          descripcion: null,
        },
        {
          capacidad_nacional_id: capacidadId("Pañales"),
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
    await renderForm([
      loteGuardado(5, "Colchones", "40.000", "unidades", "PUBLICADO"),
    ]);

    const publicados = screen.getByRole("region", { name: "Lotes ya publicados" });
    expect(publicados).toHaveTextContent("Colchones");
    expect(publicados).toHaveTextContent("40,00 unidades");
    expect(publicados).toHaveTextContent("Publicado");
    expect(screen.getByLabelText("Capacidad")).toHaveValue("");

    await completarLote(user, 0, "Abrigo", "100", "mantas");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    await screen.findByText("1 lote guardado en borrador.");
    expect(cuerpo).toEqual({
      lotes: [
        {
          capacidad_nacional_id: capacidadId("Abrigo"),
          tipo_necesidad: "Abrigo",
          cantidad_requerida: "100",
          unidad: "mantas",
          descripcion: null,
        },
      ],
    });
  });

  it("pide confirmación antes de eliminar un borrador guardado", async () => {
    let eliminaciones = 0;
    server.use(
      http.delete(`${URL_LOTES}/7`, () => {
        eliminaciones += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    await renderForm([loteGuardado(7, "Agua potable", "500.000", "litros")]);

    await user.click(screen.getByRole("button", { name: "Eliminar lote 1" }));

    expect(
      screen.getByRole("group", {
        name: "¿Eliminar el lote 1? Esta acción no se puede deshacer.",
      }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(
      screen.queryByRole("group", { name: /¿Eliminar el lote 1\?/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("Capacidad")).toHaveDisplayValue(
      "Agua potable",
    );
    expect(eliminaciones).toBe(0);
  });

  it("elimina un borrador y conserva las ediciones pendientes de los demás", async () => {
    let requestCredentials: RequestCredentials | undefined;
    let csrfHeader: string | null = null;
    let cuerpo: unknown;
    server.use(
      http.delete(`${URL_LOTES}/7`, ({ request }) => {
        requestCredentials = request.credentials;
        csrfHeader = request.headers.get("X-CSRF-Token");
        return new HttpResponse(null, { status: 204 });
      }),
      http.post(URL_LOTES, async ({ request }) => {
        cuerpo = await request.json();
        return HttpResponse.json(
          [loteGuardado(8, "Abrigo", "250.000", "mantas")],
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    await renderForm([
      loteGuardado(7, "Agua potable", "500.000", "litros"),
      loteGuardado(8, "Abrigo", "100.000", "mantas"),
    ]);

    const cantidadAbrigo = campo("Cantidad requerida", 1);
    await user.clear(cantidadAbrigo);
    await user.type(cantidadAbrigo, "250");
    await user.click(screen.getByRole("button", { name: "Eliminar lote 1" }));
    await user.click(
      screen.getByRole("button", { name: "Sí, eliminar lote 1" }),
    );

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Lote eliminado definitivamente.",
    );
    expect(requestCredentials).toBe("include");
    expect(csrfHeader).toBe(CSRF_TOKEN);
    expect(screen.getAllByLabelText("Capacidad")).toHaveLength(1);
    expect(screen.getByLabelText("Capacidad")).toHaveDisplayValue("Abrigo");
    expect(screen.getByLabelText("Cantidad requerida")).toHaveValue("250");

    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    await screen.findByText("1 lote guardado en borrador.");
    expect(cuerpo).toEqual({
      lotes: [
        {
          id: 8,
          version: 1,
          capacidad_nacional_id: capacidadId("Abrigo"),
          tipo_necesidad: "Abrigo",
          cantidad_requerida: "250",
          unidad: "mantas",
          descripcion: null,
        },
      ],
    });
  });

  it("deja una fila vacía al eliminar el único borrador", async () => {
    server.use(
      http.delete(
        `${URL_LOTES}/7`,
        () => new HttpResponse(null, { status: 204 }),
      ),
    );
    const user = userEvent.setup();
    await renderForm([loteGuardado(7, "Agua potable", "500.000", "litros")]);

    await user.click(screen.getByRole("button", { name: "Eliminar lote 1" }));
    await user.click(
      screen.getByRole("button", { name: "Sí, eliminar lote 1" }),
    );

    await screen.findByText("Lote eliminado definitivamente.");
    expect(screen.getByLabelText("Capacidad")).toHaveValue("");
    expect(
      screen.getByRole("button", { name: "Guardar borrador" }),
    ).toBeEnabled();
  });

  it("muestra el error al eliminar y conserva el lote", async () => {
    server.use(
      http.delete(`${URL_LOTES}/7`, () =>
        HttpResponse.json(
          { detail: "El lote 7 está PUBLICADO y ya no puede eliminarse." },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    await renderForm([loteGuardado(7, "Agua potable", "500.000", "litros")]);

    await user.click(screen.getByRole("button", { name: "Eliminar lote 1" }));
    await user.click(
      screen.getByRole("button", { name: "Sí, eliminar lote 1" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "El lote 7 está PUBLICADO y ya no puede eliminarse.",
    );
    expect(screen.getByLabelText("Capacidad")).toHaveDisplayValue(
      "Agua potable",
    );
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
    await renderForm();

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
    await renderForm();

    await completarLote(user, 0, "Agua potable", "500", "litros");
    await user.click(screen.getByRole("button", { name: "Guardar borrador" }));

    expect(
      await screen.findByRole("button", { name: "Guardando…" }),
    ).toBeDisabled();
    expect(screen.getByLabelText("Capacidad")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Agregar lote" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Agregar lote" }));
    expect(screen.getAllByLabelText("Capacidad")).toHaveLength(1);

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
