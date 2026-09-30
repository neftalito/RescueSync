import { useMutation, useQueryClient } from "@tanstack/react-query";

import { registrarOferta } from "../api/ofertas";
import type { OfertaFormData } from "../schemas/oferta";
import { convocatoriasAbiertasQueryKey } from "./useConvocatoriasAbiertas";
import { misOfertasQueryKey } from "./useMisOfertas";

interface RegistrarOfertaVariables {
  datos: OfertaFormData;
  csrfToken: string;
}

export function useRegistrarOferta() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ datos, csrfToken }: RegistrarOfertaVariables) =>
      registrarOferta(datos, csrfToken),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: convocatoriasAbiertasQueryKey,
      });
      void queryClient.invalidateQueries({ queryKey: misOfertasQueryKey });
    },
  });
}
