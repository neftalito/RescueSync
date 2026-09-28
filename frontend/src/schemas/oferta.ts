import { z } from "zod";

import { emergenciaResumenSchema } from "./convocatoria";

export const estadosOferta = [
  "BORRADOR",
  "PRESENTADA",
  "EN_VALIDACION",
  "VALIDADA",
  "ADJUDICADA",
  "NO_ADJUDICADA",
  "RETIRADA",
] as const;

export type EstadoOferta = (typeof estadosOferta)[number];

export const estadoOfertaLabels: Record<EstadoOferta, string> = {
  BORRADOR: "Borrador",
  PRESENTADA: "Presentada",
  EN_VALIDACION: "En validación",
  VALIDADA: "Validada",
  ADJUDICADA: "Adjudicada",
  NO_ADJUDICADA: "No adjudicada",
  RETIRADA: "Retirada",
};

export const tiposAporte = ["RECURSO", "PERSONAL", "MIXTO"] as const;

export type TipoAporte = (typeof tiposAporte)[number];

export const tipoAporteLabels: Record<TipoAporte, string> = {
  RECURSO: "Recurso",
  PERSONAL: "Personal",
  MIXTO: "Mixto",
};

export const ofertaItemSchema = z.object({
  id: z.number().int().positive(),
  lote_id: z.number().int().positive(),
  tipo: z.enum(tiposAporte),
  descripcion: z.string(),
  // Pydantic serializa `Decimal` como texto en JSON.
  cantidad_ofrecida: z.union([z.string(), z.number()]).transform(String),
  unidad: z.string(),
});

export const ofertaSchema = z.object({
  id: z.number().int().positive(),
  convocatoria_id: z.number().int().positive(),
  emergencia_id: z.number().int().positive(),
  ong_creadora_id: z.number().int().positive(),
  creada_por_usuario_id: z.number().int().positive(),
  estado: z.enum(estadosOferta),
  version_actual: z.number().int().positive(),
  observaciones: z.string().nullable(),
  presentada_en: z.string().min(1),
  creada_en: z.string().min(1),
  items: z.array(ofertaItemSchema),
  emergencia: emergenciaResumenSchema,
});

export const ofertasSchema = z.array(ofertaSchema);

export type OfertaItem = z.infer<typeof ofertaItemSchema>;
export type Oferta = z.infer<typeof ofertaSchema>;
