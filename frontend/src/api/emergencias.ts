import {
  emergenciaSchema,
  emergenciasBandejaSchema,
  type Emergencia,
  type EmergenciaBandeja,
  type EmergenciaFormData,
} from "../schemas/emergencia";
import { apiRequest } from "./client";

export function registrarEmergencia(
  datos: EmergenciaFormData,
  csrfToken: string,
): Promise<Emergencia> {
  return apiRequest("/emergencias", emergenciaSchema, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(datos),
  });
}

export function listarEmergencias(): Promise<EmergenciaBandeja[]> {
  return apiRequest("/emergencias", emergenciasBandejaSchema);
}
