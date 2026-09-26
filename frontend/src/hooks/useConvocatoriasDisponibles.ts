import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { listarConvocatoriasDisponibles } from "../api/ofertas";
import type { ConvocatoriaOfertaDisponible } from "../schemas/oferta";

export const convocatoriasDisponiblesQueryKey = [
  "ofertas",
  "convocatorias-disponibles",
] as const;

export function useConvocatoriasDisponibles(): UseQueryResult<
  ConvocatoriaOfertaDisponible[],
  Error
> {
  return useQuery({
    queryKey: convocatoriasDisponiblesQueryKey,
    queryFn: listarConvocatoriasDisponibles,
    retry: false,
    staleTime: 30_000,
  });
}