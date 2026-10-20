import { apiRequest } from "./client";
import { perfilCompetenciaSchema, type PerfilCompetencia } from "../schemas/perfiles";

export const consultarPerfilCompetencia = (): Promise<PerfilCompetencia> =>
  apiRequest("/mi-ong/perfil-competencia", perfilCompetenciaSchema);
