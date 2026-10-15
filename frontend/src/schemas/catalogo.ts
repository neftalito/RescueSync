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

export const capacidadCreateSchema = z
  .object({
    codigo: z
      .string()
      .trim()
      .toUpperCase()
      .min(1, "Ingresá un código.")
      .max(80, "El código no puede superar los 80 caracteres.")
      .regex(
        /^[A-Z][A-Z0-9_]*$/,
        "Usá letras, números y guion bajo, comenzando con una letra.",
      ),
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
  );

export type CapacidadCreate = z.infer<typeof capacidadCreateSchema>;
