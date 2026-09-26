import { z } from "zod";

export const tiposAporte = ["RECURSO", "PERSONAL", "MIXTO"] as const;

export const tipoAporteLabels: Record<(typeof tiposAporte)[number], string> = {
  RECURSO: "Recursos",
  PERSONAL: "Personal",
  MIXTO: "Recursos y personal",
};

export const loteOfertaDisponibleSchema = z.object({
  lote_id: z.number().int().positive(),
  tipo_necesidad: z.string(),
  descripcion: z.string().nullable(),
  cantidad_publicada: z.union([z.number(), z.string()]),
  unidad_publicada: z.string(),
});

export const convocatoriaOfertaDisponibleSchema = z.object({
  id: z.number().int().positive(),
  numero: z.number().int().positive(),
  emergencia_id: z.number().int().positive(),
  gravedad: z.enum(["BAJA", "MEDIA", "ALTA", "CRITICA"]),
  zona: z.string(),
  lotes: z.array(loteOfertaDisponibleSchema),
});

export const convocatoriasOfertaDisponiblesSchema = z.array(
  convocatoriaOfertaDisponibleSchema,
);

export const ofertaItemFormSchema = z.object({
  lote_id: z.number().int().positive("Elegí un lote publicado."),
  tipo: z.enum(tiposAporte, { message: "Elegí el tipo de aporte." }),
  descripcion: z
    .string()
    .trim()
    .min(1, "Describí el aporte.")
    .max(2000, "La descripción no puede superar los 2000 caracteres."),
  cantidad_ofrecida: z
    .number({ error: "Ingresá una cantidad." })
    .positive("La cantidad ofrecida debe ser mayor que cero."),
  unidad: z.string().min(1, "El lote no tiene una unidad válida."),
});

export const ofertaFormSchema = z.object({
  convocatoria_id: z.number().int().positive("Elegí una convocatoria."),
  observaciones: z
    .string()
    .trim()
    .max(4000, "Las observaciones no pueden superar los 4000 caracteres."),
  items: z.array(ofertaItemFormSchema).min(1, "Agregá al menos un lote."),
});

export const ofertaResponseSchema = z.object({
  id: z.number().int().positive(),
  convocatoria_id: z.number().int().positive(),
  emergencia_id: z.number().int().positive(),
  ong_creadora_id: z.number().int().positive(),
  creada_por_usuario_id: z.number().int().positive(),
  estado: z.string(),
  version_actual: z.number().int().positive(),
  observaciones: z.string().nullable(),
  presentada_en: z.string(),
  creada_en: z.string(),
  items: z.array(
    z.object({
      id: z.number().int().positive(),
      lote_id: z.number().int().positive(),
      tipo: z.enum(tiposAporte),
      descripcion: z.string(),
      cantidad_ofrecida: z.union([z.number(), z.string()]),
      unidad: z.string(),
    }),
  ),
});

export type ConvocatoriaOfertaDisponible = z.infer<
  typeof convocatoriaOfertaDisponibleSchema
>;
export type LoteOfertaDisponible = z.infer<typeof loteOfertaDisponibleSchema>;
export type OfertaFormData = z.infer<typeof ofertaFormSchema>;
export type Oferta = z.infer<typeof ofertaResponseSchema>;