import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { listarConvocatoriasAbiertas } from "../api/convocatorias";
import type { Convocatoria } from "../schemas/convocatoria";

export const convocatoriasAbiertasQueryKey = ["convocatorias-abiertas"] as const;

export function useConvocatoriasAbiertas(): UseQueryResult<Convocatoria[], Error> {
  return useQuery({
    queryKey: convocatoriasAbiertasQueryKey,
    queryFn: listarConvocatoriasAbiertas,
    retry: false,
    staleTime: 30_000,
  });
}
