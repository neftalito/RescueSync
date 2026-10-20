import { z } from "zod";

import { apiRequest } from "./client";
import {
  unidadSchema,
  type CapacidadCreate,
  type Unidad,
} from "../schemas/catalogo";
import { capacidadSchema, type Capacidad } from "../schemas/inventario";

export const catalogoAdminQueryKey = [
  "catalogo-nacional",
  "capacidades",
] as const;
export const unidadesQueryKey = ["catalogo-nacional", "unidades"] as const;

export function consultarCatalogoNacional(): Promise<Capacidad[]> {
  return apiRequest("/catalogo-nacional/capacidades", z.array(capacidadSchema));
}

export function consultarUnidades(): Promise<Unidad[]> {
  return apiRequest("/catalogo-nacional/unidades", z.array(unidadSchema));
}

export function crearCapacidad(
  datos: CapacidadCreate,
  csrfToken: string,
): Promise<Capacidad> {
  return apiRequest("/catalogo-nacional/capacidades", capacidadSchema, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(datos),
  });
}
