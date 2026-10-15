import { z } from "zod";
import { apiRequest } from "./client";
import {
  capacidadSchema,
  conexionSchema,
  ongNacionalSchema,
  recursoSchema,
  type RecursoForm,
  type Recurso,
  type RegistroNacionalForm,
  type OngNacional,
} from "../schemas/inventario";

export const consultarConexion = (): Promise<z.infer<typeof conexionSchema>> =>
  apiRequest("/mi-ong/conexion", conexionSchema);
export const consultarRecursos = (): Promise<Recurso[]> =>
  apiRequest("/mi-ong/recursos", z.array(recursoSchema));
export const consultarCapacidades = (): Promise<
  z.infer<typeof capacidadSchema>[]
> => apiRequest("/mi-ong/capacidades", z.array(capacidadSchema));
const cabeceras = (csrfToken: string): HeadersInit => ({
  "X-CSRF-Token": csrfToken,
});

export function registrarOngNacional(
  datos: RegistroNacionalForm,
  csrfToken: string,
): Promise<OngNacional> {
  return apiRequest("/mi-ong/registro-nacional", ongNacionalSchema, {
    method: "POST",
    headers: cabeceras(csrfToken),
    body: JSON.stringify(datos),
  });
}

export function crearRecurso(
  datos: RecursoForm,
  csrfToken: string,
): Promise<Recurso> {
  return apiRequest("/mi-ong/recursos", recursoSchema, {
    method: "POST",
    headers: cabeceras(csrfToken),
    body: JSON.stringify(datos),
  });
}
export function actualizarRecurso(
  recurso: Recurso,
  cantidadTotal: string,
  csrfToken: string,
): Promise<Recurso> {
  return apiRequest(`/mi-ong/recursos/${recurso.id}`, recursoSchema, {
    method: "PATCH",
    headers: cabeceras(csrfToken),
    body: JSON.stringify({
      cantidadTotal,
      actualizadoEn: recurso.actualizadoEn,
    }),
  });
}
