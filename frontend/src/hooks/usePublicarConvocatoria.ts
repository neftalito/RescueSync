import {
  useMutation,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { publicarConvocatoria } from "../api/convocatorias";
import { ApiError } from "../api/client";
import type { Convocatoria } from "../schemas/convocatoria";
import { emergenciasQueryKey } from "./useEmergencias";
import { convocatoriasQueryKey } from "./useConvocatorias";

export function usePublicarConvocatoria(
  emergenciaId: number,
): UseMutationResult<Convocatoria, ApiError | Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (csrfToken: string) =>
      publicarConvocatoria(emergenciaId, csrfToken),
    onSuccess: () => {
      // Publicar mueve los lotes a PUBLISHED y la emergencia a PUBLICADA, y
      // agrega una fila al listado: ambas consultas quedan desactualizadas.
      void queryClient.invalidateQueries({ queryKey: emergenciasQueryKey });
      void queryClient.invalidateQueries({ queryKey: convocatoriasQueryKey });
    },
  });
}
