import { apiRequest } from "./client";
import {
  reporteMetricasSchema,
  reporteTiemposSchema,
  type FiltrosEmergenciasMetricasForm,
  type FiltrosMetricasForm,
  type ReporteMetricas,
  type ReporteTiempos,
} from "../schemas/metricas";

function parametros(filtros: FiltrosEmergenciasMetricasForm | FiltrosMetricasForm): string {
  const params = new URLSearchParams();
  for (const [clave, valor] of Object.entries(filtros)) {
    if (valor !== "") params.set(clave, valor);
  }
  return params.toString();
}

export function consultarMetricas(
  filtros: FiltrosMetricasForm,
): Promise<ReporteMetricas> {
  return apiRequest(`/metricas?${parametros(filtros)}`, reporteMetricasSchema);
}

export function consultarTiempos(
  filtros: FiltrosEmergenciasMetricasForm,
): Promise<ReporteTiempos> {
  return apiRequest(
    `/metricas/tiempos?${parametros(filtros)}`,
    reporteTiemposSchema,
  );
}
