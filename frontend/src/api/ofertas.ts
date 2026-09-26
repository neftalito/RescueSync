import {
  convocatoriasOfertaDisponiblesSchema,
  ofertaResponseSchema,
  type Oferta,
  type OfertaFormData,
  type ConvocatoriaOfertaDisponible,
} from "../schemas/oferta";
import { apiRequest } from "./client";

export function listarConvocatoriasDisponibles(): Promise<
  ConvocatoriaOfertaDisponible[]
> {
  return apiRequest(
    "/ofertas/convocatorias",
    convocatoriasOfertaDisponiblesSchema,
  );
}

export function registrarOferta(
  datos: OfertaFormData,
  csrfToken: string,
): Promise<Oferta> {
  return apiRequest("/ofertas", ofertaResponseSchema, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(datos),
  });
}