import { useMutation, useQueryClient } from "@tanstack/react-query";

import { actualizarOferta } from "../api/ofertas";
import type { OfertaFormData } from "../schemas/oferta";
import { convocatoriasAbiertasQueryKey } from "./useConvocatoriasAbiertas";
import { misOfertasQueryKey } from "./useMisOfertas";

interface ActualizarOfertaVariables {
  ofertaId: number;
  datos: OfertaFormData;
  versionBloqueo: number;
  csrfToken: string;
}

export function useActualizarOferta() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      ofertaId,
      datos,
      versionBloqueo,
      csrfToken,
    }: ActualizarOfertaVariables) =>
      actualizarOferta(ofertaId, datos, versionBloqueo, csrfToken),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: convocatoriasAbiertasQueryKey,
      });
      void queryClient.invalidateQueries({ queryKey: misOfertasQueryKey });
    },
  });
}
