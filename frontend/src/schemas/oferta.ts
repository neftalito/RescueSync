import { z } from "zod";

import { formatearCantidad } from "../utils/cantidades";
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

function milesimas(valor: string): bigint | null {
  if (!cantidadOfrecidaPattern.test(valor)) return null;
  const [entero, fraccion = ""] = valor.replace(",", ".").split(".");
  return BigInt(entero + fraccion.padEnd(3, "0"));
}

export function calcularTotalAportes(
  aportes: ReadonlyArray<{ cantidad: string }> = [],
): string | null {
  if (aportes.length === 0) return null;

  let total = 0n;
  for (const { cantidad } of aportes) {
    const aporte = milesimas(cantidad);
    if (aporte === null || aporte <= 0n) return null;
    total += aporte;
  }

  const entero = total / 1000n;
  const fraccion = (total % 1000n).toString().padStart(3, "0").replace(/0+$/, "");
  return fraccion ? `${entero}.${fraccion}` : entero.toString();
}

const aporteFormSchema = z.object({
  recurso_nacional_id: z.string().uuid("Elegí un recurso de tu inventario."),
  cantidad: z.string().regex(cantidadOfrecidaPattern, "Ingresá una cantidad válida.").refine((v) => (milesimas(v) ?? 0n) > 0n, "La cantidad debe ser positiva."),
});

const cantidadOfrecidaFormSchema = z.string()
  .regex(
    cantidadOfrecidaPattern,
    "Ingresá una cantidad con hasta 11 enteros y 3 decimales.",
  )
  .refine(
    (valor) => Number(valor.replace(",", ".")) > 0,
    "La cantidad ofrecida debe ser mayor que cero.",
  );

export const ofertaItemFormSchema = z
  .object({
    requiere_desglose: z.boolean().optional(),
    aportes: z.array(aporteFormSchema).optional(),
    lote_id: z.number().int().positive("Elegí un lote publicado."),
    tipo: z.enum(tiposAporte, { message: "Elegí el tipo de aporte." }),
    descripcion: z
      .string()
      .trim()
      .min(1, "Describí el aporte.")
      .max(2000, "La descripción no puede superar los 2000 caracteres."),
    cantidad_ofrecida: z.string().trim(),
    cantidad_publicada: z.string().regex(cantidadOfrecidaPattern),
    unidad: z.string().min(1, "El lote no tiene una unidad válida."),
  })
  .transform((item, context) => {
    const totalAportes = calcularTotalAportes(item.aportes);
    const cantidadOfrecida = item.requiere_desglose ? totalAportes : item.cantidad_ofrecida;
    if (cantidadOfrecida === null) {
      context.addIssue({ code: "custom", path: ["aportes"], message: "Agregá recursos de tu inventario para este lote." });
      return z.NEVER;
    }

    if (!item.requiere_desglose) {
      const cantidad = cantidadOfrecidaFormSchema.safeParse(cantidadOfrecida);
      if (!cantidad.success) {
        for (const issue of cantidad.error.issues) {
          context.addIssue({ ...issue, path: ["cantidad_ofrecida"] });
        }
        return z.NEVER;
      }
      if (totalAportes !== null && milesimas(totalAportes) !== milesimas(cantidadOfrecida)) {
        context.addIssue({ code: "custom", path: ["aportes"], message: "La suma de recursos debe coincidir con la cantidad ofrecida." });
      }
    }
    if (
      Number(cantidadOfrecida.replace(",", ".")) >
      Number(item.cantidad_publicada)
    ) {
      context.addIssue({
        code: "custom",
        path: ["cantidad_ofrecida"],
        message: `La cantidad ofrecida no puede superar ${formatearCantidad(item.cantidad_publicada)} ${item.unidad}.`,
      });
    }
    return { ...item, cantidad_ofrecida: cantidadOfrecida };
  });

export const ofertaFormSchema = z.object({
  convocatoria_id: z.number().int().positive("Elegí una convocatoria."),
  observaciones: z
    .string()
    .trim()
    .max(4000, "Las observaciones no pueden superar los 4000 caracteres."),
  items: z.array(ofertaItemFormSchema).min(1, "Agregá al menos un lote."),
});

export const maxInvitadasConsorcio = 10;

export const invitacionConsorcioFormSchema = z.object({
  ongIds: z.array(z.string().regex(/^[1-9]\d*$/))
    .min(1, "Seleccioná al menos una ONG para invitar.")
    .max(maxInvitadasConsorcio, `Podés invitar hasta ${maxInvitadasConsorcio} ONGs por propuesta.`),
});

export type InvitacionConsorcioForm = z.infer<typeof invitacionConsorcioFormSchema>;

export const ofertaItemSchema = z.object({
  aportes: z.array(z.object({
    id: z.number().int(), ong_id: z.number().int(), recurso_nacional_id: z.string().uuid(),
    capacidad_nacional_id: z.string().uuid(), cantidad: z.string(), unidad: z.string(),
  })).optional(),
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
  presentada_en: z.string().min(1).nullable(),
  creada_en: z.string().min(1),
  items: z.array(ofertaItemSchema),
  emergencia: emergenciaResumenSchema,
  requiere_desglose_nacional: z.boolean().optional(),
  consorcio_editable: z.boolean().optional(),
  participantes: z.array(z.object({ ong_id: z.number().int().positive(), nombre: z.string(), rol: z.enum(["LIDER", "MIEMBRO"]), confirmada: z.boolean() })).optional(),
});

export const ofertaCreadaSchema = ofertaSchema.omit({ emergencia: true });

export const ofertasSchema = z.array(ofertaSchema);

export type OfertaItem = z.infer<typeof ofertaItemSchema>;
export type Oferta = z.infer<typeof ofertaSchema>;
export type OfertaCreada = z.infer<typeof ofertaCreadaSchema>;
export type OfertaFormData = z.infer<typeof ofertaFormSchema>;
