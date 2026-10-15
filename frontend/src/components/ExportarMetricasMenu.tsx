import { useEffect, useRef, useState, type ReactElement } from "react";
import { ActionIcon } from "./ActionIcon";
import type { ReporteMetricas, ReporteTiempos } from "../schemas/metricas";
import { descargarMetricas } from "../utils/exportarMetricas";

interface Props {
  reporte: ReporteMetricas | undefined;
  tiempos: ReporteTiempos | undefined;
  habilitado: boolean;
}

export function ExportarMetricasMenu({
  reporte,
  tiempos,
  habilitado,
}: Props): ReactElement {
  const [abierto, setAbierto] = useState(false);
  const [exportando, setExportando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const contenedor = useRef<HTMLDivElement>(null);
  const boton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!abierto) return;
    const cerrar = (event: PointerEvent): void => {
      if (
        event.target instanceof Node &&
        !contenedor.current?.contains(event.target)
      )
        setAbierto(false);
    };
    document.addEventListener("pointerdown", cerrar);
    return () => document.removeEventListener("pointerdown", cerrar);
  }, [abierto]);

  const exportar = async (formato: "csv" | "json" | "pdf"): Promise<void> => {
    if (!reporte || !habilitado) return;
    setAbierto(false);
    setExportando(true);
    setError(null);
    try {
      if (formato === "pdf") {
        const { descargarPdfMetricas } =
          await import("../utils/exportarPdfMetricas");
        await descargarPdfMetricas(reporte, tiempos);
      } else descargarMetricas(reporte, tiempos, formato);
    } catch {
      setError("No pudimos exportar el reporte. Volvé a intentarlo.");
    } finally {
      setExportando(false);
      boton.current?.focus();
    }
  };

  return (
    <div
      ref={contenedor}
      className="relative"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setAbierto(false);
          boton.current?.focus();
        }
      }}
    >
      <button
        ref={boton}
        type="button"
        disabled={!habilitado || exportando}
        aria-expanded={abierto}
        aria-controls="formatos-exportacion"
        onClick={() => setAbierto(!abierto)}
        className="action-button action-icon"
        title={exportando ? "Exportando…" : "Exportar"}
      >
        <ActionIcon name="download" />
        <span className="sr-only">{exportando ? "Exportando…" : "Exportar"}</span>
      </button>
      {abierto && (
        <div
          id="formatos-exportacion"
          aria-label="Formato de exportación"
          className="absolute right-0 z-10 mt-2 grid min-w-40 gap-1 rounded-xl border border-slate-200 bg-white p-2 shadow-lg"
        >
          {(["csv", "json", "pdf"] as const).map((formato) => (
            <button
              type="button"
              key={formato}
              onClick={() => void exportar(formato)}
              className="action-button action-primary w-full"
            >
              Exportar {formato.toUpperCase()}
            </button>
          ))}
        </div>
      )}
      {error && (
        <p role="alert" className="mt-2 max-w-64 text-sm text-red-800">
          {error}
        </p>
      )}
    </div>
  );
}
