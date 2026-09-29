import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { listarMisOfertas } from "../api/ofertas";
import type { Oferta } from "../schemas/oferta";

export const misOfertasQueryKey = ["mis-ofertas"] as const;

export function useMisOfertas(): UseQueryResult<Oferta[], Error> {
  return useQuery({
    queryKey: misOfertasQueryKey,
    queryFn: listarMisOfertas,
    retry: false,
    staleTime: 30_000,
  });
}
