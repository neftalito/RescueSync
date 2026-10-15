import { z } from "zod";
import { estados, gravedades } from "./emergencia";

export const filtrosMetricasFormSchema = z
  .object({
    fecha_desde: z.iso.date("Ingresá una fecha desde válida."),
    fecha_hasta: z.iso.date("Ingresá una fecha hasta válida."),
    municipio_id: z
      .string()
      .regex(/^$|^[1-9]\d*$/, "Elegí un municipio válido."),
    gravedad: z.union([z.enum(gravedades), z.literal("")]),
    estado: z.union([z.enum(estados), z.literal("")]),
  })
  .refine((f) => f.fecha_desde <= f.fecha_hasta, {
    message: "La fecha desde debe ser anterior o igual a la fecha hasta.",
    path: ["fecha_hasta"],
  });

export type FiltrosMetricasForm = z.infer<typeof filtrosMetricasFormSchema>;

const filtrosSchema = z.object({
  fecha_desde: z.iso.date(),
  fecha_hasta: z.iso.date(),
  municipio_id: z.number().int().positive().nullable(),
  gravedad: z.enum(gravedades).nullable(),
  estado: z.enum(estados).nullable(),
});
const conteoSchema = z.object({
  categoria: z.string(),
  cantidad: z.number().int().nonnegative(),
});
export const reporteMetricasSchema = z.object({
  generado_en: z.iso.datetime({ offset: true }),
  filtros: filtrosSchema,
  municipios: z.array(
    z.object({ id: z.number().int().positive(), nombre: z.string() }),
  ),
  resumen: z.object({
    emergencias: z.number().int().nonnegative(),
    activas: z.number().int().nonnegative(),
    resueltas: z.number().int().nonnegative(),
    convocatorias_abiertas: z.number().int().nonnegative(),
    ofertas_presentadas: z.number().int().nonnegative(),
    ong_participantes: z.number().int().nonnegative(),
  }),
  por_estado: z.array(conteoSchema),
  por_gravedad: z.array(conteoSchema),
  evolucion_mensual: z.array(conteoSchema),
  tipos_oferta: z.array(conteoSchema),
  cantidades_ofrecidas: z.array(
    z.object({
      capacidad: z.string(),
      codigo_capacidad: z.string().nullable(),
      unidad: z.string(),
      cantidad: z.string().regex(/^\d+(\.\d+)?$/),
    }),
  ),
});
export const reporteTiemposSchema = z.object({
  generado_en: z.iso.datetime({ offset: true }),
  filtros: filtrosSchema,
  disponibilidad: z.enum([
    "DISPONIBLE",
    "PARCIAL",
    "NO_DISPONIBLE",
    "SIN_DATOS",
  ]),
  casos_seleccionados: z.number().int().nonnegative(),
  casos_vinculados: z.number().int().nonnegative(),
  casos_consultados: z.number().int().nonnegative(),
  casos_con_muestras: z.number().int().nonnegative(),
  casos_sin_historial_suficiente: z.number().int().nonnegative(),
  casos_con_error: z.number().int().nonnegative(),
  muestras_descartadas: z.number().int().nonnegative(),
  etapas: z.array(
    z.object({
      etapa: z.string(),
      version_proceso: z.string(),
      promedio_segundos: z.number().nonnegative(),
      muestras: z.number().int().positive(),
    }),
  ),
});
export type ReporteMetricas = z.infer<typeof reporteMetricasSchema>;
export type ReporteTiempos = z.infer<typeof reporteTiemposSchema>;

export function filtrosInicialesMetricas(): FiltrosMetricasForm {
  const partes = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Argentina/Buenos_Aires",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const parte = (tipo: string): string =>
    partes.find((p) => p.type === tipo)?.value ?? "";
  const hoy = `${parte("year")}-${parte("month")}-${parte("day")}`;
  return {
    fecha_desde: `${hoy.slice(0, 7)}-01`,
    fecha_hasta: hoy,
    municipio_id: "",
    gravedad: "",
    estado: "",
  };
}
