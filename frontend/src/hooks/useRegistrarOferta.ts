import { useMutation, useQueryClient } from "@tanstack/react-query";

import { registrarOferta } from "../api/ofertas";
import { convocatoriasDisponiblesQueryKey } from "./useConvocatoriasDisponibles";
import type { OfertaFormData } from "../schemas/oferta";

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
        queryKey: convocatoriasDisponiblesQueryKey,
      });
    },
  });
}