import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { registrarEmergencia } from "../api/emergencias";
import { ApiError } from "../api/client";
import type { Emergencia, EmergenciaFormData } from "../schemas/emergencia";

interface RegistrarEmergenciaVariables extends EmergenciaFormData {
  csrfToken: string;
}

export function useRegistrarEmergencia(): UseMutationResult<
  Emergencia,
  ApiError | Error,
  RegistrarEmergenciaVariables
> {
  return useMutation({
    mutationFn: ({ csrfToken, ...datos }: RegistrarEmergenciaVariables) =>
      registrarEmergencia(datos, csrfToken),
  });
}
