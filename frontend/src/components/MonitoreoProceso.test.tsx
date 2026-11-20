import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { IndicadoresProceso } from "./IndicadoresProceso";
import { ActividadesBonita } from "./ActividadesBonita";
import { indicadoresProcesoSchema, type ReporteMetricas, type ReporteTiempos } from "../schemas/metricas";
import { generarCsvMetricas, crearReporteExportable } from "../utils/exportarMetricas";
import { generarPdfMetricas } from "../utils/exportarPdfMetricas";

const datos = indicadoresProcesoSchema.parse({
  emergencias_con_hechos: 1, emergencias_sin_hechos: 2,
  resolucion_por_gravedad: [{ gravedad: "ALTA", emergencias: 3, resueltas: 1, cierres_confirmados: 1, resueltas_sin_cierre: 0, con_plazo: 0, en_termino: 0, tasa_resolucion: 100 / 3, tasa_en_termino: null, promedio_segundos: 7200, promedio_en_termino_segundos: null }],
  reiteradas: [{ emergencia_id: 9, reaperturas: 1, reformulaciones: 2 }],
  ranking_ongs: [{ ong_id: 4, ong: "Ayuda", capacidad: "AGUA", unidad: "litros", cantidad: "100.125", aportes: 2, finalizados: 1, con_plazo_finalizados: 1, en_termino: 1, tasa_cumplimiento: 100 }],
  cobertura_cierres: { total: 0, parcial: 1, proporcion_total: 0, proporcion_parcial: 100 },
  demanda_rubros: [{ capacidad: "AGUA", unidad: "litros", cantidad: "200.250" }],
  alerta_adjudicacion_promedio_segundos: 3600, alerta_adjudicacion_muestras: 1,
  definiciones: ["Se seleccionan emergencias por fecha de alta."],
});
const filtros = { fecha_desde: "2026-10-01", fecha_hasta: "2026-10-15", municipio_id: null, gravedad: null, estado: null };
const locales: ReporteMetricas = {
  generado_en: "2026-10-15T12:00:00Z", filtros, municipios: [],
  resumen: { emergencias: 3, activas: 2, resueltas: 1, convocatorias_abiertas: 0, ofertas_presentadas: 2, ong_participantes: 1 },
  por_estado: [], por_gravedad: [], evolucion_mensual: [], tipos_oferta: [], cantidades_ofrecidas: [], indicadores_proceso: datos,
};
const tiempos: ReporteTiempos = {
  generado_en: locales.generado_en, filtros, disponibilidad: "SIN_DATOS", casos_seleccionados: 3,
  casos_vinculados: 1, casos_consultados: 1, casos_con_muestras: 0, casos_sin_historial_suficiente: 3,
  casos_con_error: 0, muestras_descartadas: 0, etapas: [], casos_activos_consultados: 1,
  casos_activos_con_error: 0, tareas_activas: [{ emergencia_id: 9, municipio_id: 2, gravedad: "ALTA", case_id: 42, tarea_id: 7, etapa: "Revisar necesidades", version_proceso: "1.2", estado: "ready", desde_en: "2026-10-15T09:00:00Z", antiguedad_segundos: 7200, vence_en: "2026-10-15T10:00:00Z", vencida: true }],
};
afterEach(cleanup);

describe("resultados del proceso", () => {
  it("muestra los seis indicadores, cobertura de evidencia y ausencia de plazos", () => {
    render(<IndicadoresProceso datos={datos} />);
    expect(screen.getByText(/2 sin evidencia de resultados/)).toBeInTheDocument();
    for (const titulo of ["Resolución por gravedad", "Reaperturas y reformulaciones", "ONG por recursos adjudicados y cumplimiento", "Cobertura efectiva al cierre", "Demanda por rubro", "De la alerta a la primera adjudicación efectiva"])
      expect(screen.getByRole("heading", { name: titulo })).toBeInTheDocument();
    const demanda = within(screen.getByRole("table", { name: "Demanda por rubro" }));
    expect(demanda.getAllByRole("columnheader").map(c => c.textContent)).toEqual([
      "Capacidad", "Unidad", "Necesidad publicada",
    ]);
    expect(demanda.getByRole("cell", { name: "200.250" })).toBeInTheDocument();
    expect(screen.getByText("100.125")).toBeInTheDocument();
    expect(screen.getAllByText("Sin datos")).toHaveLength(2);
    expect(screen.getByText("Se seleccionan emergencias por fecha de alta.")).toBeInTheDocument();
  });

  it("distingue tareas vencidas de consultas incompletas", () => {
    const { rerender } = render(<ActividadesBonita datos={tiempos} />);
    expect(screen.getByText("Revisar necesidades (#7)")).toBeInTheDocument();
    expect(screen.getByText(/Vencida/)).toBeInTheDocument();
    rerender(<ActividadesBonita datos={{ ...tiempos, tareas_activas: [], casos_activos_con_error: 1 }} />);
    expect(screen.getByText(/No se puede afirmar que no haya tareas pendientes/)).toBeInTheDocument();
  });

  it("exporta evidencia, definiciones, decimales y tareas en JSON, CSV y PDF", () => {
    const json = crearReporteExportable(locales, tiempos);
    expect(json.locales.indicadores_proceso).toEqual(datos);
    expect(json.locales.indicadores_proceso?.demanda_rubros).toEqual([
      { capacidad: "AGUA", unidad: "litros", cantidad: "200.250" },
    ]);
    expect(json.tiempos?.tareas_activas?.[0]?.tarea_id).toBe(7);
    const csv = generarCsvMetricas(locales, tiempos);
    for (const texto of ["ranking_ongs", "100.125", '"demanda_rubros","cantidad","AGUA / litros","200.250"', "Sin datos", "tareas_activas", datos.definiciones[0]]) expect(csv).toContain(texto);
    expect(csv).not.toContain("tasa_inhabilitacion");
    const pdf = generarPdfMetricas(locales, tiempos);
    expect(pdf.type).toBe("application/pdf");
    expect(pdf.size).toBeGreaterThan(1000);
  });
});
