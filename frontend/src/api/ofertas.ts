import { ofertasSchema, type Oferta } from "../schemas/oferta";
import { apiRequest } from "./client";

export function listarMisOfertas(): Promise<Oferta[]> {
  return apiRequest("/ofertas", ofertasSchema);
}
