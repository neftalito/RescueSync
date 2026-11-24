import { z } from "zod";
import { perfilCompetenciaSchema } from "./perfiles";

const cantidad = z.string().regex(/^\d+(\.\d{1,3})?$/);
export const validacionSchema = z.object({
  validacion: z.object({
    validacionId: z.string().uuid(), revision: z.number().int(),
    convocatoriaId: z.number().int(), vigente: z.boolean(),
    lotesCompatiblesCubiertos: z.boolean(),
    cobertura: z.array(z.object({
      loteId: z.number(), cantidadRequerida: cantidad, cantidadAsignable: cantidad,
      faltante: cantidad, unidad: z.string(),
      aportes: z.array(z.object({ aporteId: z.number(), cantidad })),
    })),
  }).nullable(),
  permiteParcial: z.boolean(),
  aportes: z.array(z.object({
    descripcion: z.string().default(""), nombreOng: z.string().default(""), tipoNecesidad: z.string().default(""),
    aporteId: z.number(), ofertaId: z.number(), version: z.number(), loteId: z.number(),
    ongId: z.number(), perfilCompetencia: perfilCompetenciaSchema.nullable(),
    cantidadOfrecida: cantidad, cantidadDisponible: cantidad, unidad: z.string(),
    admiteFracciones: z.boolean(),
  })),
  diagnosticos: z.array(z.object({
    ofertaId: z.number(), ongId: z.number(), perfilCompetencia: perfilCompetenciaSchema.nullable().default(null),
    motivos: z.array(z.object({ codigo: z.string(), mensaje: z.string() })),
  })),
});
export const adjudicacionSchema = z.object({
  adjudicacionId: z.string().uuid(), estado: z.string(), estadoIntegracion: z.string(),
  participantes: z.array(z.object({
    participacionId: z.string().uuid(), ongId: z.number(), estado: z.string(),
    compromisoIds: z.array(z.string().uuid()), finalizacionId: z.string().uuid().nullable(),
  })),
});
export const seguimientoSchema = z.object({
  idEmergencia: z.number(), estado: z.string(), puedeSolicitarCierre: z.boolean(),
  adjudicaciones: z.array(adjudicacionSchema),
  operaciones: z.array(z.object({ operacionId: z.string().uuid(), tipo: z.string(), estadoIntegracion: z.string(), etapaPendiente: z.string().nullable().optional() })).default([]),
  cierre: z.object({
    solicitudCierreId: z.string().uuid(),
    operacionCierreId: z.string().uuid(),
    operacionesInciertas: z.boolean(),
  }).nullable(),
});
export const comandosSchema = z.array(z.object({
  comandoId: z.string().uuid(), estado: z.string(), error: z.string().nullable(),
}));
export type Evaluacion = z.infer<typeof validacionSchema>;

export function milesimas(valor: string): bigint | null {
  if (!/^\d{1,11}([.,]\d{1,3})?$/.test(valor)) return null;
  const [entero, fraccion = ""] = valor.replace(",", ".").split(".");
  return BigInt(entero + fraccion.padEnd(3, "0"));
}

export function validarSeleccion(evaluacion: Evaluacion, cantidades: Record<number, string>): string | null {
  const seleccion = evaluacion.aportes.filter(a => cantidades[a.aporteId] && cantidades[a.aporteId] !== "0");
  if (!seleccion.length) return "Seleccioná al menos un aporte con cantidad positiva.";
  for (const a of seleccion) {
    const valor = milesimas(cantidades[a.aporteId] ?? "");
    if (valor === null || valor <= 0n || valor > (milesimas(a.cantidadOfrecida) ?? 0n) || (!a.admiteFracciones && valor % 1000n !== 0n)) {
      return `Revisá la cantidad del aporte ${a.aporteId}.`;
    }
  }
  return null;
}
