import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { listarEmergencias } from "../api/emergencias";
import type { EmergenciaBandeja } from "../schemas/emergencia";

export const emergenciasQueryKey = ["emergencias"] as const;

export function useEmergencias(): UseQueryResult<EmergenciaBandeja[], Error> {
  return useQuery({
    queryKey: emergenciasQueryKey,
    queryFn: listarEmergencias,
    retry: false,
    staleTime: 30_000,
  });
}
