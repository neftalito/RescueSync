import { lotesSchema, type Lote, type LotesFormData } from "../schemas/lote";
import { apiRequest } from "./client";

export function guardarLotes(
  emergenciaId: number,
  datos: LotesFormData,
  csrfToken: string,
): Promise<Lote[]> {
  const lotes = datos.lotes.map((lote) => ({
    ...(lote.id === null ? {} : { id: lote.id }),
    tipo_necesidad: lote.tipo_necesidad,
    cantidad_requerida: lote.cantidad_requerida.replace(",", "."),
    unidad: lote.unidad,
    descripcion: lote.descripcion === "" ? null : lote.descripcion,
  }));
  return apiRequest(`/emergencias/${emergenciaId}/lotes`, lotesSchema, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ lotes }),
  });
}
