import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { eliminarLote } from "../api/lotes";
import { ApiError } from "../api/client";
import { emergenciasQueryKey } from "./useEmergencias";

interface EliminarLoteVariables {
  loteId: number;
  csrfToken: string;
}

export function useEliminarLote(
  emergenciaId: number,
): UseMutationResult<void, ApiError | Error, EliminarLoteVariables> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ loteId, csrfToken }: EliminarLoteVariables) =>
      eliminarLote(emergenciaId, loteId, csrfToken),
    onSuccess: () => {
      // La clave común invalida también el listado de lotes de la emergencia.
      void queryClient.invalidateQueries({ queryKey: emergenciasQueryKey });
    },
  });
}
