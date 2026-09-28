import { convocatoriasSchema, type Convocatoria } from "../schemas/convocatoria";
import { apiRequest } from "./client";

export function listarConvocatoriasAbiertas(): Promise<Convocatoria[]> {
  return apiRequest("/convocatorias", convocatoriasSchema);
}
