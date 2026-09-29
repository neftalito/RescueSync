import {
  convocatoriaPublicadaSchema,
  convocatoriasSchema,
  type Convocatoria,
  type ConvocatoriaPublicada,
} from "../schemas/convocatoria";
import { apiRequest } from "./client";

export function listarConvocatoriasAbiertas(): Promise<Convocatoria[]> {
  return apiRequest("/convocatorias", convocatoriasSchema);
}

export function publicarConvocatoria(
  emergenciaId: number,
  csrfToken: string,
): Promise<ConvocatoriaPublicada> {
  return apiRequest(
    `/emergencias/${emergenciaId}/publicar`,
    convocatoriaPublicadaSchema,
    {
      method: "POST",
      headers: { "X-CSRF-Token": csrfToken },
    },
  );
}
