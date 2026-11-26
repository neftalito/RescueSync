import { z } from "zod";
import { estados, gravedades } from "./emergencia";

export const horasUmbrales = [8, 12, 24, 48, 72, 168, 720] as const;
const umbralHorasSchema = z.literal(horasUmbrales);
const umbralHorasFormSchema = z.enum(horasUmbrales.map(String));
const filtrosEmergenciasFormSchema = z.object({
  fecha_desde: z.iso.date("Ingresá una fecha desde válida."),
  fecha_hasta: z.iso.date("Ingresá una fecha hasta válida."),
  municipio_id: z
    .string()
    .regex(/^$|^[1-9]\d*$/, "Elegí un municipio válido."),
  gravedad: z.union([z.enum(gravedades), z.literal("")]),
  estado: z.union([z.enum(estados), z.literal("")]),
});

export const filtrosMetricasFormSchema = filtrosEmergenciasFormSchema
  .extend({
    umbral_aportes_horas: umbralHorasFormSchema,
    umbral_resolucion_horas: umbralHorasFormSchema,
  })
  .refine((f) => f.fecha_desde <= f.fecha_hasta, {
    message: "La fecha desde debe ser anterior o igual a la fecha hasta.",
    path: ["fecha_hasta"],
  });

export type FiltrosMetricasForm = z.infer<typeof filtrosMetricasFormSchema>;
export type FiltrosEmergenciasMetricasForm = z.infer<typeof filtrosEmergenciasFormSchema>;

const filtrosSchema = z.object({
  fecha_desde: z.iso.date(),
  fecha_hasta: z.iso.date(),
  municipio_id: z.number().int().positive().nullable(),
  gravedad: z.enum(gravedades).nullable(),
  estado: z.enum(estados).nullable(),
});
const filtrosMetricasSchema = filtrosSchema.extend({
  umbral_aportes_horas: umbralHorasSchema,
  umbral_resolucion_horas: umbralHorasSchema,
});
const conteoSchema = z.object({
  categoria: z.string(),
  cantidad: z.number().int().nonnegative(),
});
const porcentaje = z.number().min(0).max(100).nullable();
const segundos = z.number().nonnegative().nullable();
const cantidad = z.string().regex(/^\d+(\.\d+)?$/);
const cantidadPorRubro = z.object({
  capacidad: z.string(), unidad: z.string(), cantidad,
});
export const indicadoresProcesoSchema = z.object({
  emergencias_con_hechos: z.number().int().nonnegative(),
  emergencias_sin_hechos: z.number().int().nonnegative(),
  resolucion_por_gravedad: z.array(z.object({
    gravedad: z.enum(gravedades), emergencias: z.number().int().nonnegative(),
    resueltas: z.number().int().nonnegative(), cierres_con_tiempo: z.number().int().nonnegative(),
    cierres_confirmados: z.number().int().nonnegative(), resueltas_sin_cierre: z.number().int().nonnegative(),
    dentro_del_umbral: z.number().int().nonnegative(), tasa_resolucion: porcentaje,
    tasa_dentro_del_umbral: porcentaje, promedio_segundos: segundos,
    promedio_dentro_del_umbral_segundos: segundos,
  })),
  reiteradas: z.array(z.object({
    emergencia_id: z.number().int().positive(), reaperturas: z.number().int().nonnegative(),
    reformulaciones: z.number().int().nonnegative(),
  })),
  ranking_ongs: z.array(z.object({
    ong_id: z.number().int().positive(), ong: z.string(), capacidad: z.string(),
    unidad: z.string(), cantidad, aportes: z.number().int().positive(),
    finalizados: z.number().int().nonnegative(), finalizados_con_tiempo: z.number().int().nonnegative(),
    dentro_del_umbral: z.number().int().nonnegative(), tasa_dentro_del_umbral: porcentaje,
  })),
  cobertura_cierres: z.object({
    total: z.number().int().nonnegative(), parcial: z.number().int().nonnegative(),
    proporcion_total: porcentaje, proporcion_parcial: porcentaje,
    sin_evidencia: z.number().int().nonnegative().optional(),
  }),
  demanda_rubros: z.array(cantidadPorRubro),
  suministros_movilizados: z.object({
    cantidades: z.array(cantidadPorRubro),
    participaciones_con_registro: z.number().int().nonnegative(),
    participaciones_sin_registro: z.number().int().nonnegative(),
  }).optional(),
  resolucion_consorcios: z.object({
    con_consorcio: z.number().int().nonnegative(),
    con_adjudicacion_verificable: z.number().int().nonnegative(),
    sin_adjudicacion_verificable: z.number().int().nonnegative(),
    proporcion: porcentaje,
  }).optional(),
  alerta_adjudicacion_promedio_segundos: segundos,
  alerta_adjudicacion_muestras: z.number().int().nonnegative(),
  definiciones: z.array(z.string()),
});
export type IndicadoresProceso = z.infer<typeof indicadoresProcesoSchema>;
export const reporteMetricasSchema = z.object({
  generado_en: z.iso.datetime({ offset: true }),
  filtros: filtrosMetricasSchema,
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
  indicadores_proceso: indicadoresProcesoSchema.optional(),
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
  casos_activos_consultados: z.number().int().nonnegative().optional(),
  casos_activos_con_error: z.number().int().nonnegative().optional(),
  actividad_por_etapa: z.array(z.object({
    etapa: z.string(), version_proceso: z.string(), tareas: z.number().int().nonnegative(),
    con_fecha: z.number().int().nonnegative(), promedio_antiguedad_segundos: segundos,
    vencidas: z.number().int().nonnegative(), sin_plazo: z.number().int().nonnegative(),
    fallidas: z.number().int().nonnegative(),
  })).optional(),
  tareas_activas: z.array(z.object({
    emergencia_id: z.number().int().positive(), municipio_id: z.number().int().positive(),
    gravedad: z.enum(gravedades), case_id: z.number().int().positive(),
    tarea_id: z.number().int().positive(), etapa: z.string(), version_proceso: z.string(),
    estado: z.string(), desde_en: z.iso.datetime({ offset: true }).nullable(),
    antiguedad_segundos: segundos, vence_en: z.iso.datetime({ offset: true }).nullable(),
    vencida: z.boolean().nullable(),
  })).optional(),
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
    umbral_aportes_horas: "24",
    umbral_resolucion_horas: "72",
  };
}
