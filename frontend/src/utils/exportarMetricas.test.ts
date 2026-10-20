import { describe, expect, it } from "vitest";
import type { ReporteMetricas } from "../schemas/metricas";
import { crearReporteExportable, generarCsvMetricas } from "./exportarMetricas";

const locales: ReporteMetricas = {
  generado_en: "2026-10-15T12:00:00Z",
  filtros: {
    fecha_desde: "2026-10-01",
    fecha_hasta: "2026-10-15",
    municipio_id: 12,
    gravedad: "ALTA",
    estado: null,
  },
  municipios: [{ id: 12, nombre: "Delta" }],
  resumen: {
    emergencias: 1,
    activas: 1,
    resueltas: 0,
    convocatorias_abiertas: 0,
    ofertas_presentadas: 1,
    ong_participantes: 1,
  },
  por_estado: [],
  por_gravedad: [],
  evolucion_mensual: [],
  tipos_oferta: [],
  cantidades_ofrecidas: [
    {
      capacidad: '=SUM(1,2) "Agua"',
      codigo_capacidad: null,
      unidad: "litros",
      cantidad: "12.500",
    },
  ],
};

describe("exportación del reporte visible", () => {
  it("conserva filtros, decimales y ausencia de Bonita sin inventar ceros", () => {
    const reporte = crearReporteExportable(locales, undefined);
    expect(reporte.locales).toBe(locales);
    expect(reporte.filtros).toEqual(locales.filtros);
    expect(reporte.fuentes).toEqual({
      local: "DISPONIBLE",
      bonita: "NO_DISPONIBLE",
    });
    expect(reporte.tiempos).toBeNull();
    expect(reporte.indicadores_pendientes.every((i) => i.valor === null)).toBe(
      true,
    );
    expect(JSON.stringify(reporte)).toContain('"cantidad":"12.500"');
  });

  it("produce CSV UTF-8 con metadatos, columnas estables y escape para planillas", () => {
    const csv = generarCsvMetricas(locales, undefined);
    expect(csv).toContain(
      '"seccion","indicador","categoria","valor","unidad"\r\n',
    );
    expect(csv.startsWith("\uFEFF")).toBe(true);
    expect(csv).toContain('"filtros","municipio_id","","12",""');
    expect(csv).toContain('"\'=SUM(1,2) ""Agua"""');
    expect(csv).toContain('"12.500","litros"');
    expect(csv).toContain('"fuentes","bonita","","NO_DISPONIBLE",""');
  });
});
