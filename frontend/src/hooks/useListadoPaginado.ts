import {
  useInfiniteQuery,
  type QueryKey,
  type UseInfiniteQueryResult,
} from "@tanstack/react-query";
import type { z } from "zod";
import { consultarPagina } from "../api/paginacion";

export function useListadoPaginado<T extends { id: number | string; }>(
  queryKey: QueryKey,
  ruta: string,
  esquema: z.ZodType<T[]>,
  enabled = true,
  filtros: Record<string, string | boolean | undefined> = {},
): UseInfiniteQueryResult<T[], Error> {
  const parametros = new URLSearchParams();
  for (const [nombre, valor] of Object.entries(filtros)) {
    if (valor !== undefined && valor !== "") parametros.set(nombre, String(valor));
  }
  const rutaFiltrada = parametros.size === 0
    ? ruta
    : `${ruta}${ruta.includes("?") ? "&" : "?"}${parametros}`;
  return useInfiniteQuery({
    queryKey: parametros.size === 0 ? [...queryKey, "paginas"] : [...queryKey, filtros, "paginas"],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => consultarPagina(rutaFiltrada, esquema, pageParam),
    getNextPageParam: (ultima) => ultima.siguiente,
    select: (datos) => {
      // Una inserción concurrente puede desplazar offsets; nunca repite una tarjeta.
      const vistos = new Set<T["id"]>();
      return datos.pages.flatMap((pagina) => pagina.items).filter((item) => {
        if (vistos.has(item.id)) return false;
        vistos.add(item.id);
        return true;
      });
    },
    enabled,
    staleTime: 30_000,
    retry: false,
  });
}
