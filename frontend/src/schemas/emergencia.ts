import { z } from "zod";

export const gravedades = ["BAJA", "MEDIA", "ALTA", "CRITICA"] as const;

export type Gravedad = (typeof gravedades)[number];

export const gravedadLabels: Record<Gravedad, string> = {
  BAJA: "Baja",
  MEDIA: "Media",
  ALTA: "Alta",
  CRITICA: "Crítica",
};

export const emergenciaFormSchema = z.object({
  gravedad: z.enum(gravedades, {
    message: "Elegí la gravedad de la emergencia.",
  }),
  zona: z
    .string()
    .trim()
    .min(1, "Ingresá la zona afectada.")
    .max(255, "La zona no puede superar los 255 caracteres."),
  descripcion: z
    .string()
    .trim()
    .min(1, "Ingresá una descripción inicial.")
    .max(2000, "La descripción no puede superar los 2000 caracteres."),
});

export const estados = [
  "REGISTRADA",
  "EN_COORDINACION",
  "PUBLICADA",
  "EN_EVALUACION",
  "EN_EJECUCION",
  "RESUELTA",
  "CANCELADA",
] as const;

export type Estado = (typeof estados)[number];

export const estadoLabels: Record<Estado, string> = {
  REGISTRADA: "Registrada",
  EN_COORDINACION: "En coordinación",
  PUBLICADA: "Publicada",
  EN_EVALUACION: "En evaluación",
  EN_EJECUCION: "En ejecución",
  RESUELTA: "Resuelta",
  CANCELADA: "Cancelada",
};

export const emergenciaSchema = z.object({
  id: z.number().int().positive(),
  municipio_id: z.number().int().positive(),
  centro_coordinador_id: z.number().int().positive().nullable(),
  creada_por_usuario_id: z.number().int().positive(),
  gravedad: z.enum(gravedades),
  zona: z.string(),
  descripcion: z.string(),
  estado: z.enum(estados),
  bonita_sync: z.string().min(1),
  bonita_process_instance_id: z.number().int().positive().nullable(),
  creada_en: z.string().min(1),
  actualizada_en: z.string().min(1),
});

export const emergenciasSchema = z.array(emergenciaSchema);

/**
 * La bandeja suma los lotes que todavía se pueden publicar. Lo resuelve la base,
 * así la interfaz no pide los lotes de cada fila para decidir si ofrece la
 * acción de publicar.
 */
export const emergenciaBandejaSchema = emergenciaSchema.extend({
  cantidad_lotes_borrador: z.number().int().nonnegative(),
});

export const emergenciasBandejaSchema = z.array(emergenciaBandejaSchema);

export type EmergenciaFormData = z.infer<typeof emergenciaFormSchema>;
export type Emergencia = z.infer<typeof emergenciaSchema>;
export type EmergenciaBandeja = z.infer<typeof emergenciaBandejaSchema>;
