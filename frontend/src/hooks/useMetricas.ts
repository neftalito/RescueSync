import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { consultarMetricas, consultarTiempos } from "../api/metricas";
import type {
  FiltrosMetricasForm,
  ReporteMetricas,
  ReporteTiempos,
} from "../schemas/metricas";

export function useMetricas(filtros: FiltrosMetricasForm): {
  locales: UseQueryResult<ReporteMetricas>;
  tiempos: UseQueryResult<ReporteTiempos>;
} {
  const locales = useQuery({
    queryKey: ["metricas", "locales", filtros],
    queryFn: () => consultarMetricas(filtros),
    staleTime: 60_000,
    retry: false,
  });
  const tiempos = useQuery({
    queryKey: ["metricas", "tiempos", filtros],
    queryFn: () => consultarTiempos(filtros),
    staleTime: 60_000,
    retry: false,
  });
  return { locales, tiempos };
}
