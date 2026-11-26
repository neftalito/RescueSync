import { useQuery, type UseInfiniteQueryResult, type UseQueryResult } from "@tanstack/react-query";

import { listarEmergencias } from "../api/emergencias";
import type { EmergenciaEnBandeja } from "../schemas/emergencia";
import { emergenciasSchema, type Estado } from "../schemas/emergencia";
import { useListadoPaginado } from "./useListadoPaginado";

export const emergenciasQueryKey = ["emergencias"] as const;

export function useEmergenciasPaginadas(tieneLotes?: boolean, estado?: Estado, q = ""): UseInfiniteQueryResult<EmergenciaEnBandeja[], Error> {
  const parametros = new URLSearchParams();
  if (tieneLotes !== undefined) parametros.set("tiene_lotes", String(tieneLotes));
  if (estado !== undefined) parametros.set("estado", estado);
  return useListadoPaginado(
    [...emergenciasQueryKey, "bandeja", tieneLotes, estado],
    `/emergencias${parametros.size > 0 ? `?${parametros}` : ""}`,
    emergenciasSchema,
    true,
    { q },
  );
}

export function useEmergencias(): UseQueryResult<EmergenciaEnBandeja[], Error> {
  return useQuery({
    queryKey: emergenciasQueryKey,
    queryFn: listarEmergencias,
    retry: false,
    staleTime: 30_000,
  });
}
