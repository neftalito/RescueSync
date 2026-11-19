import { z } from "zod";

export const gravedades = ["BAJA", "MEDIA", "ALTA", "CRITICA"] as const;

export type Gravedad = (typeof gravedades)[number];

export const gravedadLabels: Record<Gravedad, string> = {
  BAJA: "Baja",
  MEDIA: "Media",
  ALTA: "Alta",
  CRITICA: "Crítica",
};

export const zonasPrioridad = [
  { codigo: "NORTE", etiqueta: "Norte" },
  { codigo: "CENTRO", etiqueta: "Centro" },
  { codigo: "SUR", etiqueta: "Sur" },
] as const;

export const emergenciaFormSchema = z.object({
  gravedad: z.enum(gravedades, {
    message: "Elegí la gravedad de la emergencia.",
  }),
  zona: z
    .string()
    .refine(
      (zona) => zonasPrioridad.some(({ codigo }) => zona === codigo),
      "Elegí la zona afectada.",
    ),
  descripcion: z
    .string()
    .trim()
    .min(1, "Ingresá una descripción inicial.")
    .max(2000, "La descripción no puede superar los 2000 caracteres."),
});

const prioridadSchema = z.number().int().min(1).max(10);

export const prioridadEmergenciaSchema = z.object({
  prioridad: prioridadSchema,
  comprobante: z.string().min(1),
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

export const estadosSincronizacionBonita = [
  "PENDIENTE",
  "VINCULADA",
  "ERROR",
  "RESULTADO_DESCONOCIDO",
] as const;

export type EstadoSincronizacionBonita =
  (typeof estadosSincronizacionBonita)[number];

export const estadoSincronizacionBonitaLabels: Record<
  EstadoSincronizacionBonita,
  string
> = {
  PENDIENTE: "Vinculación pendiente",
  VINCULADA: "Vinculada con Bonita",
  ERROR: "Error de vinculación",
  RESULTADO_DESCONOCIDO: "Vinculación por confirmar",
};

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
  prioridad: prioridadSchema.nullable().default(null),
  descripcion: z.string(),
  estado: z.enum(estados),
  bonita_sync: z.enum(estadosSincronizacionBonita),
  bonita_process_instance_id: z.number().int().positive().nullable(),
  bonita_ultimo_error: z.string().nullable().default(null),
  bonita_ultimo_intento_en: z.string().min(1).nullable().default(null),
  creada_en: z.string().min(1),
  actualizada_en: z.string().min(1),
});

export const emergenciaEnBandejaSchema = emergenciaSchema.extend({
  tiene_lotes: z.boolean(),
});

export const emergenciasSchema = z.array(emergenciaEnBandejaSchema);

export type EmergenciaFormData = z.infer<typeof emergenciaFormSchema>;
export type SolicitudPrioridad = Pick<EmergenciaFormData, "gravedad" | "zona">;
export type PrioridadEmergencia = z.infer<typeof prioridadEmergenciaSchema>;
export type Emergencia = z.infer<typeof emergenciaSchema>;
export type EmergenciaEnBandeja = z.infer<typeof emergenciaEnBandejaSchema>;
