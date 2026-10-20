import { useQuery, type UseInfiniteQueryResult, type UseQueryResult } from "@tanstack/react-query";

import { listarMisOfertas } from "../api/ofertas";
import type { Oferta } from "../schemas/oferta";
import { ofertasSchema } from "../schemas/oferta";
import { useListadoPaginado } from "./useListadoPaginado";

export const misOfertasQueryKey = ["mis-ofertas"] as const;

export function useMisOfertasPaginadas(): UseInfiniteQueryResult<Oferta[], Error> {
  return useListadoPaginado(misOfertasQueryKey, "/ofertas", ofertasSchema);
}

export function useMisOfertas(): UseQueryResult<Oferta[], Error> {
  return useQuery({
    queryKey: misOfertasQueryKey,
    queryFn: listarMisOfertas,
    retry: false,
    staleTime: 30_000,
  });
}
