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

const cantidadOfrecidaPattern = /^\d{1,11}(?:[.,]\d{1,3})?$/;

export const ofertaItemFormSchema = z
  .object({
    lote_id: z.number().int().positive("Elegí un lote publicado."),
    tipo: z.enum(tiposAporte, { message: "Elegí el tipo de aporte." }),
    descripcion: z
      .string()
      .trim()
      .min(1, "Describí el aporte.")
      .max(2000, "La descripción no puede superar los 2000 caracteres."),
    cantidad_ofrecida: z
      .string()
      .trim()
      .regex(
        cantidadOfrecidaPattern,
        "Ingresá una cantidad con hasta 11 enteros y 3 decimales.",
      )
      .refine(
        (valor) => Number(valor.replace(",", ".")) > 0,
        "La cantidad ofrecida debe ser mayor que cero.",
      ),
    cantidad_publicada: z.string().regex(cantidadOfrecidaPattern),
    unidad: z.string().min(1, "El lote no tiene una unidad válida."),
  })
  .superRefine((item, context) => {
    if (
      Number(item.cantidad_ofrecida.replace(",", ".")) >
      Number(item.cantidad_publicada)
    ) {
      context.addIssue({
        code: "custom",
        path: ["cantidad_ofrecida"],
        message: `La cantidad ofrecida no puede superar ${item.cantidad_publicada} ${item.unidad}.`,
      });
    }
  });

export const ofertaFormSchema = z.object({
  convocatoria_id: z.number().int().positive("Elegí una convocatoria."),
  observaciones: z
    .string()
    .trim()
    .max(4000, "Las observaciones no pueden superar los 4000 caracteres."),
  items: z.array(ofertaItemFormSchema).min(1, "Agregá al menos un lote."),
});

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
  version_bloqueo: z.number().int().positive(),
  editable: z.boolean(),
  observaciones: z.string().nullable(),
  presentada_en: z.string().min(1),
  creada_en: z.string().min(1),
  items: z.array(ofertaItemSchema),
  emergencia: emergenciaResumenSchema,
});

export const ofertaCreadaSchema = ofertaSchema.omit({ emergencia: true });

export const ofertasSchema = z.array(ofertaSchema);

export type OfertaItem = z.infer<typeof ofertaItemSchema>;
export type Oferta = z.infer<typeof ofertaSchema>;
export type OfertaCreada = z.infer<typeof ofertaCreadaSchema>;
export type OfertaFormData = z.infer<typeof ofertaFormSchema>;
