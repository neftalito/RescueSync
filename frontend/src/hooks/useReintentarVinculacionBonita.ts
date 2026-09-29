import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { reintentarVinculacionBonita } from "../api/emergencias";
import type { Emergencia } from "../schemas/emergencia";
import { emergenciasQueryKey } from "./useEmergencias";

interface ReintentoVariables {
  emergenciaId: number;
  csrfToken: string;
}

export function useReintentarVinculacionBonita(): UseMutationResult<
  Emergencia,
  ApiError | Error,
  ReintentoVariables
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ emergenciaId, csrfToken }) =>
      reintentarVinculacionBonita(emergenciaId, csrfToken),
    onSuccess: (actualizada) => {
      queryClient.setQueryData<Emergencia[]>(emergenciasQueryKey, (actuales) =>
        actuales?.map((emergencia) =>
          emergencia.id === actualizada.id ? actualizada : emergencia,
        ),
      );
    },
  });
}
