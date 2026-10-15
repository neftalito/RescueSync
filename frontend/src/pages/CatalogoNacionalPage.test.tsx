import "@testing-library/jest-dom/vitest";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { MemoryRouter } from "react-router";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";

import type { Session } from "../schemas/auth";
import { CatalogoNacionalPage } from "./CatalogoNacionalPage";

const API = "http://localhost:8000/api/v1/catalogo-nacional";
const unidades = [
  { codigo: "kg", nombre: "Kilogramos" },
  { codigo: "litros", nombre: "Litros" },
];
const capacidad = {
  id: "00000000-0000-4000-8000-000000000101",
  codigo: "ALIMENTOS",
  nombre: "Alimentos",
  tipo: "SUMINISTRO",
  unidad: "kg",
  admiteFracciones: true,
};
const session: Session = {
  usuario: {
    id: 7,
    email: "admin@example.org",
    rol: "ADMINISTRADOR",
    organizacion: null,
    requiere_cambio_password: false,
  },
  csrf_token: "csrf-firmado",
};
const server = setupServer(
  http.get(`${API}/unidades`, () => HttpResponse.json(unidades)),
  http.get(`${API}/capacidades`, () => HttpResponse.json([])),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

function renderPage(): QueryClient {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(["capacidades-coordinacion"], []);
  client.setQueryData(["inventario", 42, "capacidades"], []);
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CatalogoNacionalPage session={session} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}

async function completar(): Promise<ReturnType<typeof userEvent.setup>> {
  const user = userEvent.setup();
  await screen.findByRole("option", { name: "Kilogramos" });
  await user.type(screen.getByLabelText("Código"), "alimentos");
  await user.type(screen.getByLabelText("Nombre de la capacidad"), "Alimentos");
  await user.selectOptions(screen.getByLabelText("Unidad"), "kg");
  await user.click(screen.getByLabelText("Permitir cantidades fraccionadas"));
  return user;
}

describe("CatalogoNacionalPage", () => {
  it("crea usando una unidad existente y actualiza los catálogos de administración, coordinación e inventario", async () => {
    let creado = false;
    let cuerpo: unknown;
    let credenciales: RequestCredentials | undefined;
    let csrf: string | null = null;
    server.use(
      http.get(`${API}/capacidades`, () =>
        HttpResponse.json(creado ? [capacidad] : []),
      ),
      http.post(`${API}/capacidades`, async ({ request }) => {
        cuerpo = await request.json();
        credenciales = request.credentials;
        csrf = request.headers.get("X-CSRF-Token");
        creado = true;
        return HttpResponse.json(capacidad, { status: 201 });
      }),
    );
    const client = renderPage();
    const user = await completar();

    await user.click(
      screen.getByRole("button", { name: "Crear capacidad" }),
    );

    expect(
      await screen.findByText("Capacidad «Alimentos» creada."),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "Alimentos" }),
    ).toBeInTheDocument();
    expect(cuerpo).toEqual({
      codigo: "ALIMENTOS",
      nombre: "Alimentos",
      tipo: "SUMINISTRO",
      unidad: "kg",
      admiteFracciones: true,
    });
    expect(csrf).toBe("csrf-firmado");
    expect(credenciales).toBe("include");
    expect(screen.getByLabelText("Nombre de la capacidad")).toHaveValue("");
    expect(
      client.getQueryState(["capacidades-coordinacion"])?.isInvalidated,
    ).toBe(true);
    expect(
      client.getQueryState(["inventario", 42, "capacidades"])?.isInvalidated,
    ).toBe(true);
  });

  it("usa un selector de unidades predefinidas sin ofrecer un alta de unidades", async () => {
    renderPage();
    await screen.findByRole("option", { name: "Litros" });
    expect(screen.getByLabelText("Unidad").tagName).toBe("SELECT");
    expect(
      screen.queryByRole("button", { name: /crear unidad/i }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Kilogramos" })).toHaveValue(
      "kg",
    );
  });

  it("valida los campos obligatorios antes de enviar el alta", async () => {
    renderPage();
    await screen.findByRole("option", { name: "Kilogramos" });
    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: "Crear capacidad" }),
    );
    expect(await screen.findByText("Ingresá un código.")).toBeInTheDocument();
    expect(
      screen.getByText("Ingresá el nombre de la capacidad."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Elegí una unidad del catálogo."),
    ).toBeInTheDocument();
  });

  it("personal y vehículos siempre envían cantidades enteras", async () => {
    let cuerpo: unknown;
    server.use(
      http.post(`${API}/capacidades`, async ({ request }) => {
        cuerpo = await request.json();
        return HttpResponse.json(
          { ...capacidad, tipo: "PERSONAL", admiteFracciones: false },
          { status: 201 },
        );
      }),
    );
    renderPage();
    const user = await completar();
    await user.selectOptions(
      screen.getByLabelText("Tipo de recurso"),
      "PERSONAL",
    );
    const fracciones = screen.getByLabelText(
      "Permitir cantidades fraccionadas",
    );
    expect(fracciones).not.toBeChecked();
    expect(fracciones).toBeDisabled();
    await user.click(
      screen.getByRole("button", { name: "Crear capacidad" }),
    );
    await waitFor(() =>
      expect(cuerpo).toMatchObject({
        tipo: "PERSONAL",
        admiteFracciones: false,
      }),
    );
  });

  it("conserva el formulario cuando el código ya existe", async () => {
    server.use(
      http.post(`${API}/capacidades`, () =>
        HttpResponse.json(
          { detail: "Ya existe una capacidad con ese código." },
          { status: 409 },
        ),
      ),
    );
    renderPage();
    const user = await completar();
    await user.click(
      screen.getByRole("button", { name: "Crear capacidad" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Ya existe una capacidad con ese código.",
    );
    expect(screen.getByLabelText("Nombre de la capacidad")).toHaveValue(
      "Alimentos",
    );
    expect(screen.getByLabelText("Unidad")).toHaveValue("kg");
  });

  it("permite reintentar la consulta de unidades y habilita el formulario", async () => {
    let consultas = 0;
    server.use(
      http.get(`${API}/unidades`, () => {
        consultas += 1;
        return consultas === 1
          ? HttpResponse.json(
              { detail: "Catálogo temporalmente inaccesible." },
              { status: 503 },
            )
          : HttpResponse.json(unidades);
      }),
    );
    renderPage();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Catálogo temporalmente inaccesible.",
    );
    expect(
      screen.getByRole("button", { name: "Crear capacidad" }),
    ).toBeDisabled();
    const user = userEvent.setup();
    await user.click(
      screen.getByRole("button", { name: "Reintentar unidades" }),
    );
    await screen.findByRole("option", { name: "Kilogramos" });
    expect(
      screen.getByRole("button", { name: "Crear capacidad" }),
    ).toBeEnabled();
  });

  it("bloquea el alta si falta el catálogo predefinido de unidades", async () => {
    server.use(http.get(`${API}/unidades`, () => HttpResponse.json([])));
    renderPage();
    expect(
      await screen.findByText(/No hay unidades disponibles/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Crear capacidad" }),
    ).toBeDisabled();
  });
});
