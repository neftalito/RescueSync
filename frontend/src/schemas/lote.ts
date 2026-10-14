import { z } from "zod";
import { gravedades } from "./emergencia";

// Espeja `LoteItem.cantidad_requerida` (Numeric(14, 3)): hasta 11 enteros y 3
// decimales. Se envía como texto para no perder precisión con floats.
const cantidadPattern = /^\d{1,11}(?:[.,]\d{1,3})?$/;

export const estadosLote = [
  "BORRADOR",
  "PUBLICADO",
  "CERRADO",
  "CANCELADO",
] as const;

export type EstadoLote = (typeof estadosLote)[number];

export const estadoLoteLabels: Record<EstadoLote, string> = {
  BORRADOR: "Borrador",
  PUBLICADO: "Publicado",
  CERRADO: "Cerrado",
  CANCELADO: "Cancelado",
};

export const loteItemFormSchema = z.object({
  capacidad_nacional_id: z.union([z.string().uuid(), z.literal("")]).optional(),
  riesgo_requerido: z.union([z.enum(gravedades), z.literal("")]).optional(),
  id: z.number().int().positive().nullable(),
  version: z.number().int().positive().nullable(),
  tipo_necesidad: z
    .string()
    .trim()
    .min(1, "Ingresá el tipo de necesidad.")
    .max(120, "El tipo no puede superar los 120 caracteres."),
  cantidad_requerida: z
    .string()
    .trim()
    .min(1, "Ingresá la cantidad requerida.")
    .regex(
      cantidadPattern,
      "Ingresá un número con hasta 11 enteros y 3 decimales.",
    )
    .refine(
      (valor) => Number(valor.replace(",", ".")) > 0,
      "La cantidad debe ser mayor a cero.",
    ),
  unidad: z
    .string()
    .trim()
    .min(1, "Ingresá la unidad.")
    .max(40, "La unidad no puede superar los 40 caracteres."),
  descripcion: z
    .string()
    .trim()
    .max(2000, "La descripción no puede superar los 2000 caracteres."),
});

export const lotesFormSchema = z.object({
  lotes: z.array(loteItemFormSchema).min(1, "Agregá al menos un lote."),
});

export const lotePublicadoSchema = z.object({
  id: z.number().int().positive(),
  emergencia_id: z.number().int().positive(),
  tipo_necesidad: z.string(),
  descripcion: z.string().nullable(),
  // Pydantic serializa `Decimal` como texto en JSON.
  cantidad_requerida: z.union([z.string(), z.number()]).transform(String),
  unidad: z.string(),
  estado: z.enum(estadosLote),
});

export const loteSchema = lotePublicadoSchema.extend({
  capacidad_nacional_id: z.string().uuid().nullable().optional(),
  codigo_capacidad: z.string().nullable().optional(),
  riesgo_requerido: z.enum(gravedades).nullable().optional(),
  creado_por_usuario_id: z.number().int().positive(),
  version: z.number().int().positive(),
  creado_en: z.string().min(1),
  actualizado_en: z.string().min(1),
});

export const lotesSchema = z.array(loteSchema);
export const lotesPublicadosSchema = z.array(lotePublicadoSchema);

export type LoteItemFormData = z.infer<typeof loteItemFormSchema>;
export type LotesFormData = z.infer<typeof lotesFormSchema>;
export type Lote = z.infer<typeof loteSchema>;
export type LotePublicadoPublico = z.infer<typeof lotePublicadoSchema>;
