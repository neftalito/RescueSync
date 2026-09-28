import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { listarLotes, listarLotesPublicados } from "../api/lotes";
import type { Lote, LotePublicadoPublico } from "../schemas/lote";
import { emergenciasQueryKey } from "./useEmergencias";

export function lotesQueryKey(
  emergenciaId: number,
): readonly [...typeof emergenciasQueryKey, number, "lotes"] {
  return [...emergenciasQueryKey, emergenciaId, "lotes"] as const;
}

export function useLotes(emergenciaId: number): UseQueryResult<Lote[], Error> {
  return useQuery({
    queryKey: lotesQueryKey(emergenciaId),
    queryFn: () => listarLotes(emergenciaId),
    retry: false,
    staleTime: 30_000,
  });
}

export function useLotesPublicados(
  emergenciaId: number,
): UseQueryResult<LotePublicadoPublico[], Error> {
  return useQuery({
    queryKey: lotesQueryKey(emergenciaId),
    queryFn: () => listarLotesPublicados(emergenciaId),
    retry: false,
    staleTime: 30_000,
  });
}
