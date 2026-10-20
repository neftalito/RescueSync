import { z } from "zod";

import { convocatoriaSchema, emergenciaResumenSchema } from "./convocatoria";
import { estados } from "./emergencia";
import { estadosOferta, ofertaItemSchema } from "./oferta";

const emergencia = emergenciaResumenSchema.extend({
  id: z.number().int().positive(), estado: z.enum(estados),
});

const oferta = z.object({
  id: z.number().int().positive(), estado: z.enum(estadosOferta),
  version: z.number().int().positive(), presentada_en: z.string().nullable(),
  observaciones: z.string().nullable(),
  participantes: z.array(z.object({
    ong_id: z.number().int().positive(), nombre: z.string(),
    rol: z.enum(["LIDER", "MIEMBRO"]), confirmada: z.boolean(),
  })),
  items: z.array(ofertaItemSchema.extend({ necesidad: z.string() })),
});

export const detalleNotificacionSchema = z.discriminatedUnion("clase", [
  z.object({
    clase: z.literal("OFERTA_RECIBIDA"), emergencia, oferta,
    convocatoria_numero: z.number().int().positive(),
  }),
  z.object({
    clase: z.literal("CONVOCATORIA"), emergencia,
    convocatoria: convocatoriaSchema, mi_oferta: oferta.nullable(),
  }),
  z.object({
    clase: z.literal("TAREA_BONITA_FALLIDA"), emergencia,
    tarea_id: z.number().int().positive(), nombre: z.string(),
    estado_observado: z.literal("failed"), observada_en: z.string(),
  }),
]);

export type DetalleNotificacion = z.infer<typeof detalleNotificacionSchema>;
export type OfertaNotificada = z.infer<typeof oferta>;
