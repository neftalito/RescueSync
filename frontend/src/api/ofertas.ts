import {
  ofertaCreadaSchema,
  ofertasSchema,
  type Oferta,
  type OfertaCreada,
  type OfertaFormData,
} from "../schemas/oferta";
import { apiRequest } from "./client";

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
      ...datos,
      observaciones: datos.observaciones === "" ? null : datos.observaciones,
      items: datos.items.map((item) => ({
        ...item,
        cantidad_ofrecida: item.cantidad_ofrecida.replace(",", "."),
      })),
    }),
  });
}
