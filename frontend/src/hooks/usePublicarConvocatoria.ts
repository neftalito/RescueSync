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
import { actualizarPaginas } from "../utils/actualizarPaginas";
import type { EmergenciaEnBandeja } from "../schemas/emergencia";

export function usePublicarConvocatoria(
  emergenciaId: number,
): UseMutationResult<ConvocatoriaPublicada, ApiError | Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (csrfToken: string) =>
      publicarConvocatoria(emergenciaId, csrfToken),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: emergenciasQueryKey });
      actualizarPaginas<EmergenciaEnBandeja>(queryClient, [...emergenciasQueryKey, "bandeja"],
        (emergencia) => emergencia.id === emergenciaId ? { ...emergencia, estado: "PUBLICADA" } : emergencia);
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
