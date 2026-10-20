import type { ReporteMetricas, ReporteTiempos } from "../schemas/metricas";
import { etiquetasMetricas } from "./coloresMetricas";
import { filasMonitoreo } from "./filasMonitoreo";
import {
  indicadoresPendientes,
  motivoIndicadoresPendientes,
} from "./exportarMetricas";
import { capturarGraficos, type GraficoPdf } from "./pdfMetricas/capturarGraficos";
import { ConstructorPdf } from "./pdfMetricas/ConstructorPdf";
import {
  formatearEtiquetaIndicador,
  formatearFecha,
  formatearFechaHora,
  formatearNumero,
} from "./pdfMetricas/formato";

export function generarPdfMetricas(
  locales: ReporteMetricas,
  tiempos: ReporteTiempos | undefined,
  graficos: GraficoPdf[] = [],
): Blob {
  const pdf = new ConstructorPdf();
  const generado = formatearFechaHora(locales.generado_en);
  const periodo = `${formatearFecha(locales.filtros.fecha_desde)} a ${formatearFecha(locales.filtros.fecha_hasta)}`;

  pdf.encabezado(generado);
  pdf.filtros({
    periodo,
    municipio:
      locales.municipios.find((m) => m.id === locales.filtros.municipio_id)
        ?.nombre ?? "Todos",
    gravedad: etiquetasMetricas[locales.filtros.gravedad ?? ""] ?? "Todas",
    estado: etiquetasMetricas[locales.filtros.estado ?? ""] ?? "Todos",
  });

  pdf.aviso(
    "Alcance del reporte",
    [
      "Se seleccionan emergencias por fecha de alta y se informa la situación actual de sus datos relacionados. Las cantidades representan ofrecimientos.",
      `Fuentes: datos locales disponibles. Bonita: ${tiempos?.disponibilidad ?? "NO_DISPONIBLE"}.`,
    ],
    "neutro",
  );

  pdf.seccion("Resumen general");
  pdf.tarjetas(
    Object.entries(locales.resumen).map(([clave, valor]) => ({
      etiqueta: formatearEtiquetaIndicador(clave),
      valor: formatearNumero(valor),
    })),
  );

  const graficosPorTitulo = new Map(graficos.map((g) => [g.titulo, g]));
  const graficosUsados = new Set<string>();

  for (const [clave, titulo, conPorcentaje] of [
    ["evolucion_mensual", "Evolución mensual de altas", false],
    ["por_estado", "Emergencias por estado", true],
    ["por_gravedad", "Emergencias por gravedad", true],
    ["tipos_oferta", "Ofertas individuales y conjuntas", true],
  ] as const) {
    pdf.seccion(titulo);
    const filas = locales[clave].map((d) => ({
      categoria: etiquetasMetricas[d.categoria] ?? d.categoria,
      cantidad: Number(d.cantidad),
    }));
    const total = filas.reduce((suma, f) => suma + f.cantidad, 0);
    if (conPorcentaje) {
      pdf.tabla(
        ["Categoría", "Cantidad", "% del total"],
        filas.map((f) => [
          f.categoria,
          formatearNumero(f.cantidad),
          total > 0
            ? `${((f.cantidad / total) * 100).toLocaleString("es-AR", { maximumFractionDigits: 1 })} %`
            : "-",
        ]),
        [1, 2],
      );
    } else {
      pdf.tabla(
        ["Categoría", "Cantidad"],
        filas.map((f) => [f.categoria, formatearNumero(f.cantidad)]),
        [1],
      );
    }
    const g = graficosPorTitulo.get(titulo);
    if (g) {
      pdf.grafico(g, false);
      graficosUsados.add(titulo);
    }
  }

  pdf.seccion("Cantidades ofrecidas por capacidad");
  pdf.tabla(
    ["Capacidad", "Cantidad", "Unidad"],
    locales.cantidades_ofrecidas.map((c) => [
      c.capacidad,
      formatearNumero(c.cantidad),
      c.unidad,
    ]),
    [1],
  );

  if (tiempos) {
    pdf.seccion("Tiempos por tarea de Bonita");
    pdf.aviso(
      `Disponibilidad: ${tiempos.disponibilidad}`,
      [`Historial consultado: ${formatearFechaHora(tiempos.generado_en)}`],
      tiempos.disponibilidad === "DISPONIBLE" ? "ok" : "aviso",
    );
    pdf.tarjetas([
      {
        etiqueta: "Casos consultados",
        valor: `${tiempos.casos_consultados}/${tiempos.casos_vinculados}`,
      },
      {
        etiqueta: "Casos con muestras",
        valor: formatearNumero(tiempos.casos_con_muestras),
      },
      {
        etiqueta: "Sin historial suficiente",
        valor: formatearNumero(tiempos.casos_sin_historial_suficiente),
      },
      {
        etiqueta: "Sin consulta completa",
        valor: formatearNumero(tiempos.casos_con_error),
      },
      {
        etiqueta: "Muestras descartadas",
        valor: formatearNumero(tiempos.muestras_descartadas),
      },
    ]);
    pdf.tabla(
      ["Tarea", "Versión", "Promedio (horas)", "Muestras"],
      tiempos.etapas.map((e) => [
        e.etapa,
        e.version_proceso,
        (e.promedio_segundos / 3600).toLocaleString("es-AR", {
          minimumFractionDigits: 3,
          maximumFractionDigits: 3,
        }),
        e.muestras,
      ]),
      [2, 3],
    );
  }

  if (indicadoresPendientes.length) {
    pdf.aviso(
      "Indicadores no disponibles",
      indicadoresPendientes.map(
        (indicador) => `- ${indicador}: ${motivoIndicadoresPendientes}.`,
      ),
      "aviso",
    );
  }

  pdf.seccion("Resultados del proceso y actividad de Bonita");
  pdf.tabla(
    ["Sección", "Indicador", "Categoría", "Valor", "Unidad"],
    filasMonitoreo(locales, tiempos),
    [3],
  );

  const restantes = graficos.filter((g) => !graficosUsados.has(g.titulo));
  if (restantes.length) {
    pdf.seccion("Gráficos adicionales");
    for (const g of restantes) pdf.grafico(g, true);
  }

  pdf.pie(generado, periodo);
  return pdf.obtenerBlob();
}

export async function descargarPdfMetricas(
  locales: ReporteMetricas,
  tiempos: ReporteTiempos | undefined,
): Promise<void> {
  const blob = generarPdfMetricas(locales, tiempos, await capturarGraficos());
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = `rescuesync-metricas-${locales.filtros.fecha_desde}-${locales.filtros.fecha_hasta}.pdf`;
  enlace.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
