import { z } from "zod";

export const nivelRiesgoSchema = z.enum(["BAJA", "MEDIA", "ALTA", "CRITICA"]);
const motivoSchema = z.object({
  codigo: z.enum([
    "ACREDITACION_FUTURA",
    "ACREDITACION_VENCIDA",
    "ACREDITACION_REVOCADA",
    "CERTIFICACION_INACTIVA",
    "CAPACIDAD_INACTIVA",
    "ONG_PENDIENTE",
    "ONG_SUSPENDIDA",
    "ONG_BAJA",
  ]),
  mensaje: z.string(),
  capacidadId: z.uuid().nullable(),
});
const alcanceSchema = z.object({
  capacidadId: z.uuid(),
  codigo: z.string(),
  nombre: z.string(),
  tipo: z.enum(["PERSONAL", "VEHICULO", "EQUIPAMIENTO", "SUMINISTRO"]),
  unidad: z.string(),
  admiteFracciones: z.boolean(),
  activa: z.boolean(),
  riesgoMaximo: nivelRiesgoSchema,
});
export const certificacionSchema = z.object({
  id: z.uuid(),
  codigo: z.string(),
  revision: z.number().int().positive(),
  nombre: z.string(),
  activa: z.boolean(),
  alcances: z.array(alcanceSchema),
});
export const certificacionesOngSchema = z.object({
  ongId: z.uuid(),
  estadoOng: z.enum(["PENDIENTE", "HABILITADA", "SUSPENDIDA", "BAJA"]),
  evaluadoEn: z.iso.datetime({ offset: true }),
  acreditaciones: z.array(
    z.object({
      id: z.uuid(),
      certificacion: certificacionSchema,
      emisor: z.string(),
      numeroCredencial: z.string(),
      vigenteDesde: z.iso.datetime({ offset: true }),
      vigenteHasta: z.iso.datetime({ offset: true }),
      estado: z.enum(["OTORGADA", "REVOCADA"]),
      estadoVigencia: z.enum(["FUTURA", "VIGENTE", "VENCIDA", "REVOCADA"]),
      revocadaEn: z.iso.datetime({ offset: true }).nullable(),
      motivoRevocacion: z.string().nullable(),
      motivos: z.array(motivoSchema),
    }),
  ),
  capacidadesHabilitadas: z.array(
    z.object({
      capacidadId: z.uuid(),
      codigo: z.string(),
      nombre: z.string(),
      unidad: z.string(),
      riesgoMaximo: nivelRiesgoSchema,
      nivelesRiesgoPermitidos: z.array(nivelRiesgoSchema),
      acreditacionIds: z.array(z.uuid()),
    }),
  ),
  motivosInstitucionales: z.array(motivoSchema),
});

export type Certificacion = z.infer<typeof certificacionSchema>;
export type CertificacionesOng = z.infer<typeof certificacionesOngSchema>;
