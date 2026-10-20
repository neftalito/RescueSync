import { jsPDF } from "jspdf";
import { autoTable, type RowInput } from "jspdf-autotable";
import type { GraficoPdf } from "./capturarGraficos";
import {
  ANCHO,
  BORDE,
  DERECHA,
  FILA_ALTERNA,
  FONDO_TARJETA,
  FONDO_UTIL,
  GRIS,
  MARGEN,
  PAGINA_ANCHO,
  PRIMARIO,
  PRIMARIO_CLARO,
  TEXTO,
  TONOS,
  TOPE,
  type RGB,
  type Tono,
} from "./estilos";

interface FiltrosPdf {
  periodo: string;
  municipio: string;
  gravedad: string;
  estado: string;
}

/** Dibuja los bloques del reporte y administra el espacio y la paginación. */
export class ConstructorPdf {
  private readonly doc = new jsPDF({ compress: true });
  private y = 0;
  private seccionActual = 0;

  constructor() {
    this.doc.setProperties({ title: "RescueSync - Dashboard de auditoría" });
  }

  private asegurar(alto: number): void {
    if (this.y + alto > FONDO_UTIL) {
      this.doc.addPage();
      this.y = TOPE;
    }
  }

  private fijarTexto(
    tamano: number,
    color: RGB = TEXTO,
    estilo: "normal" | "bold" = "normal",
  ): void {
    this.doc.setFont("helvetica", estilo);
    this.doc.setFontSize(tamano);
    this.doc.setTextColor(...color);
  }

  seccion(titulo: string): void {
    this.seccionActual += 1;
    this.asegurar(40);
    this.doc.setFillColor(...PRIMARIO);
    this.doc.roundedRect(MARGEN, this.y - 5, 1.8, 8, 0.9, 0.9, "F");
    this.fijarTexto(13, TEXTO, "bold");
    this.doc.text(`${this.seccionActual}. ${titulo}`, MARGEN + 5, this.y + 1);
    this.doc.setDrawColor(...BORDE);
    this.doc.setLineWidth(0.3);
    this.doc.line(MARGEN, this.y + 5, DERECHA, this.y + 5);
    this.fijarTexto(10);
    this.y += 12;
  }

  aviso(titulo: string, lineas: string[], tono: Tono): void {
    const { fondo, barra } = TONOS[tono];
    this.fijarTexto(9);
    const envueltas = lineas.flatMap(
      (linea): string[] => this.doc.splitTextToSize(linea, ANCHO - 10),
    );
    const alto = (titulo ? 8 : 3) + envueltas.length * 4.2 + 4;
    this.asegurar(alto + 4);
    this.doc.setFillColor(...fondo);
    this.doc.roundedRect(MARGEN, this.y, ANCHO, alto, 1.5, 1.5, "F");
    this.doc.setFillColor(...barra);
    this.doc.roundedRect(MARGEN, this.y, 1.8, alto, 0.9, 0.9, "F");
    let cursor = this.y + 5.5;
    if (titulo) {
      this.fijarTexto(9.5, TEXTO, "bold");
      this.doc.text(titulo, MARGEN + 6, cursor);
      cursor += 5;
    }
    this.fijarTexto(9, TEXTO);
    for (const linea of envueltas) {
      this.doc.text(linea, MARGEN + 6, cursor);
      cursor += 4.2;
    }
    this.y += alto + 6;
  }

  tarjetas(items: { etiqueta: string; valor: string }[]): void {
    const columnas = 3;
    const separacion = 4;
    const ancho = (ANCHO - separacion * (columnas - 1)) / columnas;
    const alto = 22;
    for (let i = 0; i < items.length; i += columnas) {
      this.asegurar(alto + separacion);
      items.slice(i, i + columnas).forEach((item, j) => {
        const x = MARGEN + j * (ancho + separacion);
        this.doc.setFillColor(...FONDO_TARJETA);
        this.doc.setDrawColor(...BORDE);
        this.doc.setLineWidth(0.3);
        this.doc.roundedRect(x, this.y, ancho, alto, 2, 2, "FD");
        this.doc.setFillColor(...PRIMARIO);
        this.doc.roundedRect(x, this.y, 1.8, alto, 0.9, 0.9, "F");
        this.fijarTexto(8, GRIS);
        this.doc.text(
          (this.doc.splitTextToSize(item.etiqueta, ancho - 10) as string[])[0] ?? "",
          x + 6,
          this.y + 7,
        );
        this.fijarTexto(17, PRIMARIO, "bold");
        this.doc.text(item.valor, x + 6, this.y + 16.5);
      });
      this.y += alto + separacion;
    }
    this.fijarTexto(10);
    this.y += 4;
  }

  tabla(
    cabecera: string[],
    cuerpo: (string | number)[][],
    alinearDerecha: number[] = [],
  ): void {
    const body: RowInput[] = cuerpo.length
      ? cuerpo
      : [
          [
            {
              content: "Sin datos",
              colSpan: cabecera.length,
              styles: { halign: "center", textColor: GRIS, fontStyle: "italic" },
            },
          ],
        ];
    const columnStyles = Object.fromEntries(
      alinearDerecha.map((i) => [i, { halign: "right" as const }]),
    );
    autoTable(this.doc, {
      startY: this.y,
      head: [cabecera],
      body,
      margin: { left: MARGEN, right: MARGEN, top: 20, bottom: 18 },
      styles: {
        fontSize: 9,
        cellPadding: { top: 2.4, bottom: 2.4, left: 3, right: 3 },
        overflow: "linebreak",
        textColor: TEXTO,
        lineColor: BORDE,
        lineWidth: 0.1,
      },
      headStyles: {
        fillColor: PRIMARIO,
        textColor: 255,
        fontStyle: "bold",
        lineWidth: 0,
      },
      alternateRowStyles: { fillColor: FILA_ALTERNA },
      columnStyles,
      didDrawPage: ({ cursor }) => {
        this.y = (cursor?.y ?? TOPE) + 8;
      },
    });
    this.fijarTexto(10);
  }

  grafico(g: GraficoPdf, conTitulo: boolean): void {
    if (conTitulo) {
      this.asegurar(20);
      this.fijarTexto(11, TEXTO, "bold");
      this.doc.text(g.titulo, MARGEN, this.y);
      this.y += 6;
    }
    if (!g.imagen) {
      this.aviso(
        "",
        [
          `No fue posible incorporar el gráfico "${g.titulo}". Consultar la tabla de datos.`,
        ],
        "aviso",
      );
      return;
    }
    const maxAncho = ANCHO - 8;
    const maxAlto = 95;
    let ancho = maxAncho;
    let alto = ancho * g.proporcion;
    if (alto > maxAlto) {
      alto = maxAlto;
      ancho = alto / g.proporcion;
    }
    const caja = alto + 8;
    this.asegurar(caja + 4);
    this.doc.setDrawColor(...BORDE);
    this.doc.setLineWidth(0.3);
    this.doc.roundedRect(MARGEN, this.y, ANCHO, caja, 2, 2, "S");
    this.doc.addImage(
      g.imagen,
      "PNG",
      MARGEN + (ANCHO - ancho) / 2,
      this.y + 4,
      ancho,
      alto,
    );
    this.y += caja + 8;
  }

  encabezado(generado: string): void {
    this.doc.setFillColor(...PRIMARIO);
    this.doc.rect(0, 0, PAGINA_ANCHO, 42, "F");
    this.doc.setFillColor(...PRIMARIO_CLARO);
    this.doc.rect(0, 42, PAGINA_ANCHO, 2, "F");
    this.fijarTexto(24, [255, 255, 255], "bold");
    this.doc.text("RescueSync", MARGEN, 21);
    this.fijarTexto(12, [207, 250, 254]);
    this.doc.text("Dashboard de auditoría", MARGEN, 30);
    this.fijarTexto(8, [207, 250, 254]);
    this.doc.text("GENERADO", DERECHA, 18, { align: "right" });
    this.fijarTexto(10, [255, 255, 255], "bold");
    this.doc.text(generado, DERECHA, 24, { align: "right" });
    this.fijarTexto(8, [207, 250, 254]);
    this.doc.text("Hora de Argentina", DERECHA, 29.5, { align: "right" });
    this.y = 56;
  }

  filtros({ periodo, municipio, gravedad, estado }: FiltrosPdf): void {
    const filtros: [string, string, number][] = [
      ["PERÍODO DE ALTA", periodo, 62],
      ["MUNICIPIO", municipio, 44],
      ["GRAVEDAD", gravedad, 36],
      ["ESTADO", estado, 36],
    ];
    this.doc.setFillColor(...FONDO_TARJETA);
    this.doc.setDrawColor(...BORDE);
    this.doc.setLineWidth(0.3);
    this.doc.roundedRect(MARGEN, this.y, ANCHO, 20, 2, 2, "FD");
    let x = MARGEN + 5;
    for (const [etiqueta, valor, ancho] of filtros) {
      this.fijarTexto(7.5, GRIS, "bold");
      this.doc.text(etiqueta, x, this.y + 7);
      this.fijarTexto(10, TEXTO, "bold");
      const lineas: string[] = this.doc.splitTextToSize(valor, ancho - 6);
      this.doc.text(lineas.slice(0, 2), x, this.y + 13, { lineHeightFactor: 1.1 });
      x += ancho;
    }
    this.y += 27;
  }

  pie(generado: string, periodo: string): void {
    const total = this.doc.getNumberOfPages();
    for (let pagina = 1; pagina <= total; pagina++) {
      this.doc.setPage(pagina);
      if (pagina > 1) {
        this.fijarTexto(8, GRIS);
        this.doc.text("RescueSync | Dashboard de auditoría", MARGEN, 11);
        this.doc.text(`Período: ${periodo}`, DERECHA, 11, { align: "right" });
        this.doc.setDrawColor(...PRIMARIO);
        this.doc.setLineWidth(0.4);
        this.doc.line(MARGEN, 14, DERECHA, 14);
      }
      this.doc.setDrawColor(...BORDE);
      this.doc.setLineWidth(0.3);
      this.doc.line(MARGEN, 283, DERECHA, 283);
      this.fijarTexto(8, GRIS);
      this.doc.text(`Generado el ${generado}`, MARGEN, 288);
      this.doc.text(`Página ${pagina} de ${total}`, DERECHA, 288, { align: "right" });
    }
  }

  obtenerBlob(): Blob {
    return this.doc.output("blob");
  }
}
