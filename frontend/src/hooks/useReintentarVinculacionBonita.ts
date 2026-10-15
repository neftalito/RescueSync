import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { reintentarVinculacionBonita } from "../api/emergencias";
import type { Emergencia } from "../schemas/emergencia";
import { emergenciasQueryKey } from "./useEmergencias";
import { actualizarPaginas } from "../utils/actualizarPaginas";
import type { EmergenciaEnBandeja } from "../schemas/emergencia";

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
      actualizarPaginas<EmergenciaEnBandeja>(queryClient, [...emergenciasQueryKey, "bandeja"],
        (emergencia) => emergencia.id === actualizada.id ? { ...emergencia, ...actualizada } : emergencia);
      queryClient.setQueryData<Emergencia[]>(emergenciasQueryKey, (actuales) =>
        actuales?.map((emergencia) =>
          emergencia.id === actualizada.id
            ? { ...emergencia, ...actualizada }
            : emergencia,
        ),
      );
    },
  });
}
