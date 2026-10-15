import { z } from "zod";

export const conexionSchema = z.object({
  estado: z.enum(["LISTA", "SIN_CONFIGURAR", "REQUIERE_REVISION"]),
  vinculada: z.boolean(),
  conectada: z.boolean(),
  ongId: z.uuid().nullable(),
  expiraEn: z.string().nullable(),
});
export const registroNacionalFormSchema = z.object({
  emailContacto: z
    .union([z.email("Ingresá un email de contacto válido."), z.literal("")])
    .optional(),
});
export const ongNacionalSchema = z.object({
  id: z.uuid(),
  nombre: z.string(),
  estado: z.enum(["PENDIENTE", "HABILITADA", "SUSPENDIDA", "BAJA"]),
});

export const capacidadSchema = z.object({
  id: z.uuid(),
  codigo: z.string(),
  nombre: z.string(),
  tipo: z.enum(["PERSONAL", "VEHICULO", "EQUIPAMIENTO", "SUMINISTRO"]),
  unidad: z.string(),
  admiteFracciones: z.boolean(),
});

export const cantidadSchema = z
  .string()
  .regex(
    /^(?:0|[1-9]\d{0,10})(?:\.\d{1,3})?$/,
    "Ingresá una cantidad válida con hasta 3 decimales y punto decimal.",
  );
const cantidadPositivaSchema = cantidadSchema.pipe(
  z.string().refine(
    (valor) => cantidadEnMiles(valor) > 0n,
    "La cantidad debe ser mayor que cero.",
  ),
);
export const recursoSchema = z.object({
  id: z.uuid(),
  ongId: z.uuid(),
  capacidadId: z.uuid(),
  codigoInterno: z.string(),
  nombre: z.string(),
  capacidad: z.string(),
  unidad: z.string(),
  admiteFracciones: z.boolean(),
  cantidadTotal: cantidadSchema,
  cantidadComprometida: cantidadSchema,
  cantidadDisponible: cantidadSchema,
  activo: z.boolean(),
  actualizadoEn: z.string(),
});
export const recursoFormSchema = z.object({
  capacidadId: z.uuid("Seleccioná una capacidad."),
  codigoInterno: z.string().trim().min(1, "Ingresá un código interno.").max(80),
  nombre: z.string().trim().min(1, "Ingresá el nombre del recurso.").max(160),
  cantidadTotal: cantidadPositivaSchema,
});
export const cantidadFormSchema = recursoFormSchema.pick({ cantidadTotal: true });
export const vinculoFormSchema = z.object({
  ong_nacional_id: z.union([z.uuid("Ingresá un UUID válido."), z.literal("")]),
});

export type RegistroNacionalForm = z.infer<typeof registroNacionalFormSchema>;
export type OngNacional = z.infer<typeof ongNacionalSchema>;
export type ConexionEstado = z.infer<typeof conexionSchema>;
export type Recurso = z.infer<typeof recursoSchema>;
export type Capacidad = z.infer<typeof capacidadSchema>;
export type RecursoForm = z.infer<typeof recursoFormSchema>;
export type CantidadForm = z.infer<typeof cantidadFormSchema>;
export type VinculoForm = z.infer<typeof vinculoFormSchema>;

export function cantidadEnMiles(valor: string): bigint {
  const [entero = "0", fraccion = ""] = valor.split(".");
  return BigInt(entero) * 1000n + BigInt(fraccion.padEnd(3, "0"));
}
