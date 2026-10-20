import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, describe, expect, it } from "vitest";
import { z } from "zod";
import { useListadoPaginado } from "../hooks/useListadoPaginado";
import { ListadoLocal, ListadoRemoto } from "./ListadoProgresivo";

const esquema = z.array(z.object({ id: z.number(), nombre: z.string() }));
const filas = Array.from({ length: 43 }, (_, indice) => ({
  id: indice + 1, nombre: `Registro ${indice + 1}`,
}));
const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => { cleanup(); server.resetHandlers(); });
afterAll(() => server.close());

function ListadoPrueba({ filtro = "todos" }: { filtro?: string; }) {
  const query = useListadoPaginado(["prueba", filtro], `/prueba?filtro=${filtro}`, esquema);
  if (!query.data) return <p role="status">Cargando listado…</p>;
  return <ListadoRemoto query={query} etiqueta="Registros">
    <ul>{query.data.map((fila) => <li key={fila.id}>{fila.nombre}</li>)}</ul>
  </ListadoRemoto>;
}

function renderListado(filtro = "todos") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const vista = (valor: string) => <QueryClientProvider client={client}><ListadoPrueba filtro={valor} /></QueryClientProvider>;
  const resultado = render(vista(filtro));
  return (valor: string) => resultado.rerender(vista(valor));
}

describe("listados progresivos", () => {
  it("pide páginas acotadas, conserva las filas ante un fallo y permite recuperar el resto", async () => {
    const offsets: number[] = [];
    let falloPendiente = true;
    server.use(http.get("http://localhost:8000/api/v1/prueba", ({ request }) => {
      const url = new URL(request.url);
      const offset = Number(url.searchParams.get("offset"));
      const limit = Number(url.searchParams.get("limit"));
      offsets.push(offset);
      expect(limit).toBe(21);
      expect(request.credentials).toBe("include");
      if (offset === 20 && falloPendiente) {
        falloPendiente = false;
        return HttpResponse.json({ detail: "Fallo temporal" }, { status: 503 });
      }
      return HttpResponse.json(filas.slice(offset, offset + limit));
    }));
    const user = userEvent.setup();
    renderListado();
    expect(await screen.findByText("Registro 20")).toBeInTheDocument();
    expect(screen.queryByText("Registro 21")).not.toBeInTheDocument();
    expect(offsets).toEqual([0]);
    await user.click(screen.getByRole("button", { name: "Cargar más" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Podés reintentar");
    expect(screen.getAllByRole("listitem")).toHaveLength(20);
    await user.click(screen.getByRole("button", { name: "Reintentar carga" }));
    expect(await screen.findByText("Registro 40")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cargar más" }));
    expect(await screen.findByText("Registro 43")).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(43);
    expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
    expect(offsets).toEqual([0, 20, 20, 40]);
  });

  it("reinicia la consulta al cambiar de filtro sin mezclar páginas", async () => {
    const consultas: string[] = [];
    server.use(http.get("http://localhost:8000/api/v1/prueba", ({ request }) => {
      const url = new URL(request.url);
      const filtro = url.searchParams.get("filtro") ?? "";
      consultas.push(`${filtro}:${url.searchParams.get("offset")}`);
      return HttpResponse.json(filtro === "otros" ? [{ id: 90, nombre: "Otro registro" }] : filas.slice(0, 21));
    }));
    const cambiarFiltro = renderListado();
    await screen.findByText("Registro 20");
    cambiarFiltro("otros");
    expect(await screen.findByText("Otro registro")).toBeInTheDocument();
    expect(screen.queryByText("Registro 1")).not.toBeInTheDocument();
    expect(consultas).toEqual(["todos:0", "otros:0"]);
  });

  it("muestra reportes completos por bloques sin perder las últimas filas", async () => {
    render(<ListadoLocal items={filas} etiqueta="Reporte">
      {(visibles) => <ul>{visibles.map((fila) => <li key={fila.id}>{fila.nombre}</li>)}</ul>}
    </ListadoLocal>);
    const user = userEvent.setup();
    expect(screen.getAllByRole("listitem")).toHaveLength(20);
    expect(screen.getByRole("region", { name: "Reporte" })).toHaveAttribute("tabindex", "0");
    await user.click(screen.getByRole("button", { name: "Cargar más" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(40);
    await user.click(screen.getByRole("button", { name: "Cargar más" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(43);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
