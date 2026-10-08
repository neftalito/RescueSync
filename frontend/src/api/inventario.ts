import { z } from "zod";
import { apiRequest, apiRequestVoid } from "./client";
import {
  capacidadSchema,
  conexionSchema,
  recursoSchema,
  type ConexionForm,
  type RecursoForm,
  type Recurso,
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

export function conectarCuenta(
  datos: ConexionForm,
  csrfToken: string,
): Promise<z.infer<typeof conexionSchema>> {
  return apiRequest("/mi-ong/conexion", conexionSchema, {
    method: "POST",
    headers: cabeceras(csrfToken),
    body: JSON.stringify(datos),
  });
}
export function desconectarCuenta(csrfToken: string): Promise<void> {
  return apiRequestVoid("/mi-ong/conexion", {
    method: "DELETE",
    headers: cabeceras(csrfToken),
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
