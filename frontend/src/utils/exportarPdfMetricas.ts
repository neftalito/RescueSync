import { jsPDF } from "jspdf";
import { autoTable } from "jspdf-autotable";
import type { ReporteMetricas, ReporteTiempos } from "../schemas/metricas";
import { etiquetasMetricas } from "./coloresMetricas";
import { filasMonitoreo } from "./filasMonitoreo";
import {
  indicadoresPendientes,
  motivoIndicadoresPendientes,
} from "./exportarMetricas";

interface GraficoPdf {
  titulo: string;
  imagen: string | null;
  /** alto / ancho del gráfico original */
  proporcion: number;
}

const PROPORCION_POR_DEFECTO = 0.54;

/**
 * Devuelve el SVG del gráfico dentro del panel. Recharts también dibuja los
 * íconos de la leyenda como <svg class="recharts-surface"> (14x14), por lo que
 * se descartan los que están dentro de la leyenda y se elige el de mayor área.
 */
function encontrarSvgGrafico(panel: HTMLElement): SVGSVGElement | null {
  const candidatos = Array.from(
    panel.querySelectorAll<SVGSVGElement>("svg.recharts-surface"),
  ).filter((svg) => !svg.closest(".recharts-legend-wrapper"));

  const area = (svg: SVGSVGElement): number => {
    const { width, height } = svg.getBoundingClientRect();
    return width * height;
  };

  candidatos.sort((a, b) => area(b) - area(a));
  return candidatos[0] ?? null;
}

async function capturarGraficos(): Promise<GraficoPdf[]> {
  const graficos: GraficoPdf[] = [];
  for (const panel of document.querySelectorAll<HTMLElement>(
    "[data-reporte-grafico]",
  )) {
    const svg = encontrarSvgGrafico(panel);
    if (!svg) continue;
    const titulo = panel.dataset.reporteGrafico ?? "Gráfico";
    try {
      const { width, height } = svg.getBoundingClientRect();
      if (!width || !height) throw new Error("Gráfico sin dimensiones.");
      const copia = svg.cloneNode(true);
      if (!(copia instanceof SVGSVGElement)) continue;
      copia.setAttribute("xmlns", "http://www.w3.org/2000/svg");
      copia.setAttribute("width", String(width));
      copia.setAttribute("height", String(height));
      copia.style.fontFamily = "Arial, sans-serif";
      const imagen = new Image();
      imagen.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(copia))}`;
      await imagen.decode();
      const canvas = document.createElement("canvas");
      canvas.width = Math.ceil(width * 2);
      canvas.height = Math.ceil(height * 2);
      const contexto = canvas.getContext("2d");
      if (!contexto) throw new Error("No se pudo preparar el gráfico.");
      contexto.fillStyle = "white";
      contexto.fillRect(0, 0, canvas.width, canvas.height);
      contexto.drawImage(imagen, 0, 0, canvas.width, canvas.height);
      graficos.push({
        titulo,
        imagen: canvas.toDataURL("image/png"),
        proporcion: height / width,
      });
    } catch {
      graficos.push({
        titulo,
        imagen: null,
        proporcion: PROPORCION_POR_DEFECTO,
      });
    }
  }
  return graficos;
}

export function generarPdfMetricas(
  locales: ReporteMetricas,
  tiempos: ReporteTiempos | undefined,
  graficos: GraficoPdf[] = [],
): Blob {
  const doc = new jsPDF({ compress: true });
  let y = 20;
  const texto = (contenido: string, tamano = 10): void => {
    doc.setFontSize(tamano);
    const lineas: string[] = doc.splitTextToSize(contenido, 178);
    const alto = lineas.length * tamano * 0.45 + 4;
    if (y + alto > 278) {
      doc.addPage();
      y = 20;
    }
    doc.text(lineas, 16, y);
    y += alto;
  };
  const tabla = (
    titulo: string,
    cabecera: string[],
    cuerpo: (string | number)[][],
  ): void => {
    if (y > 240) {
      doc.addPage();
      y = 20;
    }
    texto(titulo, 12);
    autoTable(doc, {
      startY: y,
      head: [cabecera],
      body: cuerpo.length ? cuerpo : [["Sin datos"]],
      margin: { left: 16, right: 16, top: 18, bottom: 18 },
      styles: { fontSize: 9, cellPadding: 2.5, overflow: "linebreak" },
      headStyles: { fillColor: [14, 116, 144] },
      didDrawPage: ({ cursor }) => {
        y = (cursor?.y ?? 20) + 10;
      },
    });
  };
  doc.setProperties({ title: "RescueSync - Dashboard de auditoría" });
  texto("RescueSync - Dashboard de auditoría", 18);
  texto(
    `Generado: ${new Date(locales.generado_en).toLocaleString("es-AR", { timeZone: "America/Argentina/Buenos_Aires" })} (Argentina)`,
  );
  texto(
    `Período de alta: ${locales.filtros.fecha_desde} a ${locales.filtros.fecha_hasta}`,
  );
  texto(
    `Municipio: ${locales.municipios.find((m) => m.id === locales.filtros.municipio_id)?.nombre ?? "Todos"}. Gravedad: ${etiquetasMetricas[locales.filtros.gravedad ?? ""] ?? "Todas"}. Estado: ${etiquetasMetricas[locales.filtros.estado ?? ""] ?? "Todos"}.`,
  );
  texto(
    "Se seleccionan emergencias por fecha de alta y se informa la situación actual de sus datos relacionados. Las cantidades representan ofrecimientos.",
  );
  texto(
    `Fuentes: datos locales disponibles. Bonita: ${tiempos?.disponibilidad ?? "NO_DISPONIBLE"}.`,
  );
  tabla(
    "Resumen",
    ["Indicador", "Cantidad"],
    Object.entries(locales.resumen).map(([k, v]) => [
      k.replaceAll("_", " "),
      v,
    ]),
  );
  for (const [clave, titulo] of [
    ["evolucion_mensual", "Evolución mensual de altas"],
    ["por_estado", "Emergencias por estado"],
    ["por_gravedad", "Emergencias por gravedad"],
    ["tipos_oferta", "Ofertas individuales y conjuntas"],
  ] as const) {
    tabla(
      titulo,
      ["Categoría", "Cantidad"],
      locales[clave].map((d) => [
        etiquetasMetricas[d.categoria] ?? d.categoria,
        d.cantidad,
      ]),
    );
  }
  tabla(
    "Cantidades ofrecidas por capacidad",
    ["Capacidad", "Cantidad", "Unidad"],
    locales.cantidades_ofrecidas.map((c) => [
      c.capacidad,
      c.cantidad,
      c.unidad,
    ]),
  );
  if (tiempos) {
    texto(
      `Bonita: ${tiempos.casos_consultados}/${tiempos.casos_vinculados} casos consultados; ${tiempos.casos_con_muestras} con muestras; ${tiempos.casos_sin_historial_suficiente} sin historial suficiente; ${tiempos.casos_con_error} sin consulta completa; ${tiempos.muestras_descartadas} muestras descartadas.`,
    );
    texto(`Historial consultado: ${tiempos.generado_en}`);
    tabla(
      "Tiempos por tarea de Bonita",
      ["Tarea", "Versión", "Promedio (horas)", "Muestras"],
      tiempos.etapas.map((e) => [
        e.etapa,
        e.version_proceso,
        (e.promedio_segundos / 3600).toFixed(3),
        e.muestras,
      ]),
    );
  }
  for (const indicador of indicadoresPendientes)
    texto(`${indicador}: ${motivoIndicadoresPendientes}.`);
  tabla(
    "Resultados del proceso y actividad de Bonita",
    ["Sección", "Indicador", "Categoría", "Valor", "Unidad"],
    filasMonitoreo(locales, tiempos),
  );
  for (const grafico of graficos) {
    const ancho = 178;
    const alto = ancho * grafico.proporcion;
    // título (~10 mm) + imagen + margen inferior
    if (y + alto + 16 > 278) {
      doc.addPage();
      y = 20;
    }
    texto(grafico.titulo, 12);
    if (grafico.imagen) {
      doc.addImage(grafico.imagen, "PNG", 16, y, ancho, alto);
      y += alto + 10;
    } else
      texto(
        "No fue posible incorporar la imagen. Consultar la tabla de datos del gráfico.",
      );
  }
  for (let pagina = 1; pagina <= doc.getNumberOfPages(); pagina++) {
    doc.setPage(pagina);
    doc.setFontSize(8);
    doc.setTextColor(100);
    doc.text(`RescueSync | ${pagina} / ${doc.getNumberOfPages()}`, 16, 289);
  }
  return doc.output("blob");
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