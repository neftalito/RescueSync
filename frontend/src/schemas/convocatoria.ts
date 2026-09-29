import { z } from "zod";

import { gravedades } from "./emergencia";

export const estadosConvocatoria = ["ABIERTA", "CERRADA", "CANCELADA"] as const;
export const estadosTareaBonita = [
  "PENDIENTE",
  "EN_PROGRESO",
  "COMPLETADA",
  "ERROR",
  "RESULTADO_DESCONOCIDO",
] as const;

export type EstadoConvocatoria = (typeof estadosConvocatoria)[number];

export const estadoConvocatoriaLabels: Record<EstadoConvocatoria, string> = {
  ABIERTA: "Abierta",
  CERRADA: "Cerrada",
  CANCELADA: "Cancelada",
};

export const lotePublicadoSchema = z.object({
  lote_id: z.number().int().positive(),
  tipo_necesidad: z.string().min(1),
  descripcion: z.string().nullable(),
  // Pydantic serializa `Decimal` como texto en JSON.
  cantidad_publicada: z.union([z.string(), z.number()]).transform(String),
  unidad_publicada: z.string(),
});

export const emergenciaResumenSchema = z.object({
  zona: z.string(),
  gravedad: z.enum(gravedades),
  descripcion: z.string(),
});

export const convocatoriaSchema = z.object({
  id: z.number().int().positive(),
  emergencia_id: z.number().int().positive(),
  numero: z.number().int().positive(),
  estado: z.enum(estadosConvocatoria),
  publicada_en: z.string().min(1),
  cierra_en: z.string().min(1),
  lotes: z.array(lotePublicadoSchema),
  emergencia: emergenciaResumenSchema,
});

export const convocatoriaPublicadaSchema = z.object({
  id: z.number().int().positive(),
  emergencia_id: z.number().int().positive(),
  numero: z.number().int().positive(),
  estado: z.enum(estadosConvocatoria),
  publicada_en: z.string().min(1),
  cierra_en: z.string().min(1),
  lotes: z.array(lotePublicadoSchema),
  bonita_generar_lotes_estado: z.enum(estadosTareaBonita),
  bonita_generar_lotes_ultimo_error: z.string().nullable(),
  bonita_generar_lotes_ultimo_intento_en: z.string().min(1).nullable(),
});

export const convocatoriasSchema = z.array(convocatoriaSchema);

export type LotePublicado = z.infer<typeof lotePublicadoSchema>;
export type EmergenciaResumen = z.infer<typeof emergenciaResumenSchema>;
export type Convocatoria = z.infer<typeof convocatoriaSchema>;
export type ConvocatoriaPublicada = z.infer<typeof convocatoriaPublicadaSchema>;
