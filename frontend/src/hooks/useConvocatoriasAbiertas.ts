import { useQuery, type UseInfiniteQueryResult, type UseQueryResult } from "@tanstack/react-query";

import { listarConvocatoriasAbiertas } from "../api/convocatorias";
import type { Convocatoria } from "../schemas/convocatoria";
import { convocatoriasSchema } from "../schemas/convocatoria";
import { useListadoPaginado } from "./useListadoPaginado";

export const convocatoriasAbiertasQueryKey = ["convocatorias-abiertas"] as const;

export function useConvocatoriasPaginadas(q = "", zona = ""): UseInfiniteQueryResult<Convocatoria[], Error> {
  return useListadoPaginado(convocatoriasAbiertasQueryKey, "/convocatorias", convocatoriasSchema, true, { q, zona });
}

export function useConvocatoriasAbiertas(): UseQueryResult<Convocatoria[], Error> {
  return useQuery({
    queryKey: convocatoriasAbiertasQueryKey,
    queryFn: listarConvocatoriasAbiertas,
    retry: false,
    staleTime: 30_000,
  });
}
