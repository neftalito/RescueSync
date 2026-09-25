import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { guardarLotes } from "../api/lotes";
import { ApiError } from "../api/client";
import { emergenciasQueryKey } from "./useEmergencias";
import type { Lote, LotesFormData } from "../schemas/lote";

interface GuardarLotesVariables extends LotesFormData {
  csrfToken: string;
}

export function useGuardarLotes(
  emergenciaId: number,
): UseMutationResult<Lote[], ApiError | Error, GuardarLotesVariables> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ csrfToken, ...datos }: GuardarLotesVariables) =>
      guardarLotes(emergenciaId, datos, csrfToken),
    onSuccess: () => {
      // Guardar el primer lote asigna el centro coordinador a la emergencia.
      void queryClient.invalidateQueries({ queryKey: emergenciasQueryKey });
    },
  });
}
