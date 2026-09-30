import { apiRequest } from "./client";
import {
  notificacionSchema,
  notificacionesLeidasSchema,
  notificacionesSchema,
  type Notificacion,
  type NotificacionesLeidas,
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

export function marcarTodasLasNotificacionesLeidas(
  csrfToken: string,
): Promise<NotificacionesLeidas> {
  return apiRequest("/notificaciones/leidas", notificacionesLeidasSchema, {
    method: "PATCH",
    headers: { "X-CSRF-Token": csrfToken },
  });
}
