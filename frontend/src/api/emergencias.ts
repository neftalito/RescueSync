import {
  emergenciaSchema,
  emergenciasSchema,
  type Emergencia,
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

export function listarEmergencias(): Promise<Emergencia[]> {
  return apiRequest("/emergencias", emergenciasSchema);
}

export function reintentarVinculacionBonita(
  emergenciaId: number,
  csrfToken: string,
): Promise<Emergencia> {
  return apiRequest(
    `/emergencias/${emergenciaId}/reintentar-bonita`,
    emergenciaSchema,
    {
      method: "POST",
      headers: { "X-CSRF-Token": csrfToken },
    },
  );
}
