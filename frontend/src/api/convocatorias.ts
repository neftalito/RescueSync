import {
  convocatoriaSchema,
  convocatoriasListSchema,
  type Convocatoria,
  type ConvocatoriaResumen,
  type EstadoConvocatoria,
} from "../schemas/convocatoria";
import { apiRequest } from "./client";

export function listarConvocatorias(
  estado?: EstadoConvocatoria,
): Promise<ConvocatoriaResumen[]> {
  const query = estado === undefined ? "" : `?estado=${estado}`;
  return apiRequest(
    `/convocatorias${query}`,
    convocatoriasListSchema,
  ).then((respuesta) => respuesta.items);
}

export function publicarConvocatoria(
  emergenciaId: number,
  csrfToken: string,
): Promise<Convocatoria> {
  return apiRequest(`/emergencias/${emergenciaId}/publicar`, convocatoriaSchema, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}
