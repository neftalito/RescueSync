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
): UseInfiniteQueryResult<T[], Error> {
  return useInfiniteQuery({
    queryKey: [...queryKey, "paginas"],
    initialPageParam: 0,
    queryFn: ({ pageParam }) => consultarPagina(ruta, esquema, pageParam),
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
