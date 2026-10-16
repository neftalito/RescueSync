import { apiRequest, apiRequestVoid } from "./client";
import { comandosSchema, seguimientoSchema, validacionSchema } from "../schemas/ejecucion";

const base = (id: number) => `/emergencias/${id}`;
export const consultarEvaluacion = (id: number) => apiRequest(`${base(id)}/ofertas-validadas`, validacionSchema);
export const consultarSeguimiento = (id: number) => apiRequest(`${base(id)}/adjudicaciones`, seguimientoSchema);
export const consultarComandos = (id: number) => apiRequest(`${base(id)}/comandos-bonita`, comandosSchema);

export async function enviarComando(id: number, ruta: string, csrf: string, body?: object): Promise<void> {
  await apiRequestVoid(`${base(id)}/${ruta}`, {
    method: "POST", headers: { "X-CSRF-Token": csrf },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}
