import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { publicarConvocatoria } from "../api/convocatorias";
import type { ConvocatoriaPublicada } from "../schemas/convocatoria";
import type { Emergencia } from "../schemas/emergencia";
import { convocatoriasAbiertasQueryKey } from "./useConvocatoriasAbiertas";
import { emergenciasQueryKey } from "./useEmergencias";

export function usePublicarConvocatoria(
  emergenciaId: number,
): UseMutationResult<ConvocatoriaPublicada, ApiError | Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (csrfToken: string) =>
      publicarConvocatoria(emergenciaId, csrfToken),
    onSuccess: () => {
      queryClient.setQueryData<Emergencia[]>(emergenciasQueryKey, (actuales) =>
        actuales?.map((emergencia) =>
          emergencia.id === emergenciaId
            ? { ...emergencia, estado: "PUBLICADA" }
            : emergencia,
        ),
      );
      void queryClient.invalidateQueries({
        queryKey: convocatoriasAbiertasQueryKey,
      });
    },
  });
}
