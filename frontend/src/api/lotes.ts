import {
  lotesPublicadosSchema,
  lotesSchema,
  type Lote,
  type LotePublicadoPublico,
  type LotesFormData,
} from "../schemas/lote";
import { apiRequest, apiRequestVoid } from "./client";

export function listarLotes(emergenciaId: number): Promise<Lote[]> {
  return apiRequest(`/emergencias/${emergenciaId}/lotes`, lotesSchema);
}

export function listarLotesPublicados(
  emergenciaId: number,
): Promise<LotePublicadoPublico[]> {
  return apiRequest(
    `/emergencias/${emergenciaId}/lotes`,
    lotesPublicadosSchema,
  );
}

export function guardarLotes(
  emergenciaId: number,
  datos: LotesFormData,
  csrfToken: string,
): Promise<Lote[]> {
  const lotes = datos.lotes.map((lote) => ({
    ...(lote.id === null
      ? {}
      : { id: lote.id, version: lote.version }),
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

export function eliminarLote(
  emergenciaId: number,
  loteId: number,
  csrfToken: string,
): Promise<void> {
  return apiRequestVoid(`/emergencias/${emergenciaId}/lotes/${loteId}`, {
    method: "DELETE",
    headers: { "X-CSRF-Token": csrfToken },
  });
}
