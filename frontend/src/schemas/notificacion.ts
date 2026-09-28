import { z } from "zod";

export const tiposNotificacion = [
  "EMERGENCIA_REGISTRADA",
  "EMERGENCIA_ESTADO_ACTUALIZADO",
  "CONVOCATORIA_PUBLICADA",
  "CONVOCATORIA_ACTUALIZADA",
  "CONVOCATORIA_CERRADA",
  "OFERTA_RECIBIDA",
] as const;

export const notificacionSchema = z.object({
  id: z.number().int().positive(),
  usuario_id: z.number().int().positive(),
  tipo: z.enum(tiposNotificacion),
  titulo: z.string().min(1),
  mensaje: z.string().min(1),
  ruta: z.string().startsWith("/").nullable(),
  leida_en: z.string().datetime({ offset: true }).nullable(),
  creada_en: z.string().datetime({ offset: true }),
});

export const notificacionesSchema = z.array(notificacionSchema);

export const notificacionesLeidasSchema = z.object({
  cantidad_actualizada: z.number().int().nonnegative(),
  leida_en: z.string().datetime({ offset: true }),
});

export const eventoNotificacionSchema = z.object({
  evento: z.literal("notificacion.creada"),
  notificacion: notificacionSchema,
});

export type Notificacion = z.infer<typeof notificacionSchema>;
export type NotificacionesLeidas = z.infer<typeof notificacionesLeidasSchema>;
export type TipoNotificacion = Notificacion["tipo"];
