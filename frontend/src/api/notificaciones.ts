import { apiRequest } from "./client";
import {
  notificacionSchema,
  notificacionesSchema,
  type Notificacion,
} from "../schemas/notificacion";

export function listarNotificaciones(): Promise<Notificacion[]> {
  return apiRequest("/notificaciones", notificacionesSchema);
}

export function marcarNotificacionLeida(
  notificacionId: number,
  csrfToken: string,
): Promise<Notificacion> {
  return apiRequest(
    `/notificaciones/${notificacionId}/leida`,
    notificacionSchema,
    {
      method: "PATCH",
      headers: { "X-CSRF-Token": csrfToken },
    },
  );
}
