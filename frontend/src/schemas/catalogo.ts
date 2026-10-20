import { z } from "zod";

import { capacidadSchema, type Capacidad } from "./inventario";

export const unidadSchema = z.object({
  codigo: z.string(),
  nombre: z.string(),
});
export type Unidad = z.infer<typeof unidadSchema>;

export const tipoCapacidadLabels: Record<Capacidad["tipo"], string> = {
  PERSONAL: "Personal",
  VEHICULO: "Vehículos",
  EQUIPAMIENTO: "Equipamiento",
  SUMINISTRO: "Suministros",
};

/** Deriva el identificador del nombre y elimina tildes para el catálogo nacional. */
export function generarCodigoCapacidad(nombre: string): string {
  return nombre
    .trim()
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toUpperCase()
    .replace(/\s+/gu, "-");
}

export const capacidadCreateSchema = z
  .object({
    nombre: z
      .string()
      .trim()
      .min(1, "Ingresá el nombre de la capacidad.")
      .max(160, "El nombre no puede superar los 160 caracteres."),
    tipo: capacidadSchema.shape.tipo,
    unidad: z.string().min(1, "Elegí una unidad del catálogo.").max(40),
    admiteFracciones: z.boolean(),
  })
  .refine(
    (datos) =>
      !["PERSONAL", "VEHICULO"].includes(datos.tipo) || !datos.admiteFracciones,
    {
      message: "Personal y vehículos requieren cantidades enteras.",
      path: ["admiteFracciones"],
    },
  )
  .superRefine((datos, ctx) => {
    if (!datos.nombre) return;
    const codigo = generarCodigoCapacidad(datos.nombre);
    if (codigo.length > 80) {
      ctx.addIssue({
        code: "custom",
        path: ["nombre"],
        message: "El código generado no puede superar los 80 caracteres. Abreviá el nombre.",
      });
    }
    if (!/^[A-Z][A-Z0-9_-]*$/.test(codigo)) {
      ctx.addIssue({
        code: "custom",
        path: ["nombre"],
        message: "Usá un nombre que empiece con una letra y contenga letras, números, espacios o guiones.",
      });
    }
  })
  .transform((datos) => ({ ...datos, codigo: generarCodigoCapacidad(datos.nombre) }));

export type CapacidadForm = z.input<typeof capacidadCreateSchema>;
export type CapacidadCreate = z.output<typeof capacidadCreateSchema>;
