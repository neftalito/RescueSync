import { z } from "zod";
import { apiRequest } from "./client";

export const TAMANO_PAGINA = 20;

export interface Pagina<T> {
  items: T[];
  siguiente: number | undefined;
}

export async function consultarPagina<T>(
  ruta: string,
  esquema: z.ZodType<T[]>,
  offset: number,
): Promise<Pagina<T>> {
  const separador = ruta.includes("?") ? "&" : "?";
  // Una fila adicional permite detectar el final sin contar toda la colección.
  const items = await apiRequest(
    `${ruta}${separador}limit=${TAMANO_PAGINA + 1}&offset=${offset}`,
    esquema,
  );
  return {
    items: items.slice(0, TAMANO_PAGINA),
    siguiente: items.length > TAMANO_PAGINA ? offset + TAMANO_PAGINA : undefined,
  };
}
