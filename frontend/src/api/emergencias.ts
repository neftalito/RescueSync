import {
  emergenciaSchema,
  emergenciasSchema,
  prioridadEmergenciaSchema,
  type Emergencia,
  type EmergenciaEnBandeja,
  type EmergenciaFormData,
  type PrioridadEmergencia,
  type SolicitudPrioridad,
} from "../schemas/emergencia";
import { apiRequest } from "./client";

export function consultarPrioridad(
  datos: SolicitudPrioridad,
  csrfToken: string,
): Promise<PrioridadEmergencia> {
  return apiRequest("/emergencias/prioridad", prioridadEmergenciaSchema, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(datos),
  });
}

export function registrarEmergencia(
  datos: EmergenciaFormData & { comprobante_prioridad: string },
  csrfToken: string,
): Promise<Emergencia> {
  return apiRequest("/emergencias", emergenciaSchema, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(datos),
  });
}

export function listarEmergencias(): Promise<EmergenciaEnBandeja[]> {
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
