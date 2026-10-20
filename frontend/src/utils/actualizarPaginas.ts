import type { InfiniteData, QueryClient, QueryKey } from "@tanstack/react-query";
import type { Pagina } from "../api/paginacion";

/** Refleja una mutación en todas las ventanas ya consultadas de un listado. */
export function actualizarPaginas<T>(
  client: QueryClient,
  queryKey: QueryKey,
  actualizar: (item: T) => T,
): void {
  client.setQueriesData<InfiniteData<Pagina<T>>>({
    queryKey,
    predicate: (query) => query.queryKey.at(-1) === "paginas",
  }, (datos) => datos && ({
    ...datos,
    pages: datos.pages.map((pagina) => ({
      ...pagina,
      items: pagina.items.map(actualizar),
    })),
  }));
}
