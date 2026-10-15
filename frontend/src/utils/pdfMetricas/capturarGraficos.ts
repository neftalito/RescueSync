export interface GraficoPdf {
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
export function encontrarSvgGrafico(panel: HTMLElement): SVGSVGElement | null {
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

export async function capturarGraficos(): Promise<GraficoPdf[]> {
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

