import {
  ofertaCreadaSchema,
  ofertasSchema,
  type Oferta,
  type OfertaCreada,
  type OfertaFormData,
} from "../schemas/oferta";
import { apiRequest } from "./client";

interface ContenidoOfertaApi {
  observaciones: string | null;
  items: Array<{
    lote_id: number;
    tipo: OfertaFormData["items"][number]["tipo"];
    descripcion: string;
    cantidad_ofrecida: string;
    unidad: string;
    aportes?: Array<{ recurso_nacional_id: string; cantidad: string }>;
  }>;
}

function contenidoOferta(datos: OfertaFormData): ContenidoOfertaApi {
  return {
    observaciones: datos.observaciones === "" ? null : datos.observaciones,
    items: datos.items.map((item) => ({
      lote_id: item.lote_id,
      tipo: item.tipo,
      descripcion: item.descripcion,
      cantidad_ofrecida: item.cantidad_ofrecida.replace(",", "."),
      unidad: item.unidad,
      ...(item.aportes?.length ? { aportes: item.aportes.map((a) => ({ recurso_nacional_id: a.recurso_nacional_id, cantidad: a.cantidad.replace(",", ".") })) } : {}),
    })),
  };
}

export function listarMisOfertas(): Promise<Oferta[]> {
  return apiRequest("/ofertas", ofertasSchema);
}

export function registrarOferta(
  datos: OfertaFormData,
  csrfToken: string,
): Promise<OfertaCreada> {
  return apiRequest("/ofertas", ofertaCreadaSchema, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify({
      convocatoria_id: datos.convocatoria_id,
      ...contenidoOferta(datos),
    }),
  });
}

export function actualizarOferta(
  ofertaId: number,
  datos: OfertaFormData,
  versionBloqueo: number,
  csrfToken: string,
): Promise<OfertaCreada> {
  return apiRequest(`/ofertas/${ofertaId}`, ofertaCreadaSchema, {
    method: "PUT",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify({
      version_bloqueo: versionBloqueo,
      ...contenidoOferta(datos),
    }),
  });
}
