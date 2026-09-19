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

export const emergenciaSchema = z.object({
  id: z.number().int().positive(),
  municipio_id: z.number().int().positive(),
  centro_coordinador_id: z.number().int().positive().nullable(),
  creada_por_usuario_id: z.number().int().positive(),
  gravedad: z.enum(gravedades),
  zona: z.string(),
  descripcion: z.string(),
  estado: z.string().min(1),
  bonita_sync: z.string().min(1),
  bonita_process_instance_id: z.number().int().positive().nullable(),
  creada_en: z.string().min(1),
  actualizada_en: z.string().min(1),
});

export type EmergenciaFormData = z.infer<typeof emergenciaFormSchema>;
export type Emergencia = z.infer<typeof emergenciaSchema>;
