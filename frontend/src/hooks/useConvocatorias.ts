import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { listarConvocatorias } from "../api/convocatorias";
import type { ConvocatoriaResumen, EstadoConvocatoria } from "../schemas/convocatoria";

export const convocatoriasQueryKey = ["convocatorias"] as const;

export function useConvocatorias(
  estado?: EstadoConvocatoria,
): UseQueryResult<ConvocatoriaResumen[], Error> {
  return useQuery({
    // El estado forma parte de la clave para que cambiar el filtro no mezcle
    // los resultados de dos consultas distintas en la misma caché.
    queryKey: [...convocatoriasQueryKey, estado ?? "TODAS"],
    queryFn: () => listarConvocatorias(estado),
    retry: false,
    staleTime: 30_000,
  });
}
