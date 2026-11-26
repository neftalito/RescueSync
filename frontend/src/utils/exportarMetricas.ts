import type { ReporteMetricas, ReporteTiempos } from "../schemas/metricas";
import { filasMonitoreo } from "./filasMonitoreo";

export function indicadoresPendientes(locales: ReporteMetricas): string[] {
  const datos = locales.indicadores_proceso;
  return [
    ...(!datos?.suministros_movilizados ? ["Suministros movilizados"] : []),
    ...(!datos?.resolucion_consorcios ? ["Resolución mediante consorcios"] : []),
  ];
}

export const motivoIndicadoresPendientes = "El servidor no incluyó el indicador.";

interface ReporteExportable {
  generado_en: string;
  interpretacion: string;
  zona_horaria: string;
  filtros: ReporteMetricas["filtros"];
  fuentes: { local: "DISPONIBLE"; bonita: ReporteTiempos["disponibilidad"] };
  locales: ReporteMetricas;
  tiempos: ReporteTiempos | null;
  indicadores_pendientes: { indicador: string; valor: null; motivo: string }[];
}

export function crearReporteExportable(
  locales: ReporteMetricas,
  tiempos: ReporteTiempos | undefined,
): ReporteExportable {
  return {
    generado_en: locales.generado_en,
    interpretacion:
      "Emergencias por fecha de alta; situación actual de sus datos relacionados.",
    zona_horaria: "America/Argentina/Buenos_Aires",
    filtros: locales.filtros,
    fuentes: {
      local: "DISPONIBLE",
      bonita: tiempos?.disponibilidad ?? "NO_DISPONIBLE",
    },
    locales,
    tiempos: tiempos ?? null,
    indicadores_pendientes: indicadoresPendientes(locales).map((indicador) => ({
      indicador,
      valor: null,
      motivo: motivoIndicadoresPendientes,
    })),
  };
}

// El entrecomillado CSV no evita que una planilla ejecute fórmulas de nombres externos.
function celdaCsv(valor: string | number): string {
  const texto = String(valor);
  const seguro = /^[\s]*[=+@-]/.test(texto) ? `'${texto}` : texto;
  return `"${seguro.replaceAll('"', '""')}"`;
}

export function generarCsvMetricas(
  locales: ReporteMetricas,
  tiempos: ReporteTiempos | undefined,
): string {
  const filas: (string | number)[][] = [
    ["seccion", "indicador", "categoria", "valor", "unidad"],
  ];
  filas.push(["metadatos", "generado_en", "", locales.generado_en, "UTC"]);
  filas.push([
    "metadatos",
    "interpretacion",
    "",
    "Emergencias por fecha de alta; situación actual de sus datos relacionados",
    "",
  ]);
  filas.push([
    "metadatos",
    "zona_horaria",
    "",
    "America/Argentina/Buenos_Aires",
    "",
  ]);
  filas.push(
    ["fuentes", "local", "", "DISPONIBLE", ""],
    ["fuentes", "bonita", "", tiempos?.disponibilidad ?? "NO_DISPONIBLE", ""],
  );
  for (const [clave, valor] of Object.entries(locales.filtros))
    filas.push(["filtros", clave, "", valor ?? "Todos", clave.endsWith("_horas") ? "horas" : ""]);
  for (const [clave, valor] of Object.entries(locales.resumen))
    filas.push(["resumen", clave, "", valor, "cantidad"]);
  for (const clave of [
    "por_estado",
    "por_gravedad",
    "evolucion_mensual",
    "tipos_oferta",
  ] as const) {
    for (const fila of locales[clave])
      filas.push([
        clave,
        "cantidad",
        fila.categoria,
        fila.cantidad,
        "cantidad",
      ]);
  }
  for (const fila of locales.cantidades_ofrecidas)
    filas.push([
      "cantidades_ofrecidas",
      fila.capacidad,
      fila.codigo_capacidad ?? "Sin código",
      fila.cantidad,
      fila.unidad,
    ]);
  if (tiempos) {
    filas.push(["bonita", "generado_en", "", tiempos.generado_en, "UTC"]);
    for (const clave of [
      "casos_seleccionados",
      "casos_vinculados",
      "casos_consultados",
      "casos_con_muestras",
      "casos_sin_historial_suficiente",
      "casos_con_error",
      "muestras_descartadas",
    ] as const)
      filas.push(["bonita", clave, "", tiempos[clave], "cantidad"]);
    for (const fila of tiempos.etapas) {
      filas.push([
        "tiempos",
        fila.etapa,
        fila.version_proceso,
        fila.promedio_segundos,
        "segundos",
      ]);
      filas.push([
        "muestras",
        fila.etapa,
        fila.version_proceso,
        fila.muestras,
        "cantidad",
      ]);
    }
  }
  for (const indicador of indicadoresPendientes(locales))
    filas.push(["pendientes", indicador, "", motivoIndicadoresPendientes, ""]);
  filas.push(...filasMonitoreo(locales, tiempos));
  return `\uFEFF${filas.map((fila) => fila.map(celdaCsv).join(",")).join("\r\n")}\r\n`;
}

export function descargarMetricas(
  locales: ReporteMetricas,
  tiempos: ReporteTiempos | undefined,
  formato: "json" | "csv",
): void {
  const contenido =
    formato === "json"
      ? JSON.stringify(crearReporteExportable(locales, tiempos), null, 2)
      : generarCsvMetricas(locales, tiempos);
  const blob = new Blob([contenido], {
    type:
      formato === "json"
        ? "application/json;charset=utf-8"
        : "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = `rescuesync-metricas-${locales.filtros.fecha_desde}-${locales.filtros.fecha_hasta}.${formato}`;
  enlace.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
