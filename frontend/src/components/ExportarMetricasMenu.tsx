import { useEffect, useRef, useState, type ReactElement } from "react";
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
        className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
      >
        {exportando ? "Exportando…" : "Exportar"}{" "}
        <span aria-hidden="true">▾</span>
      </button>
      {abierto && (
        <div
          id="formatos-exportacion"
          aria-label="Formato de exportación"
          className="absolute right-0 z-10 mt-2 min-w-40 rounded-xl border border-slate-200 bg-white p-1 shadow-lg"
        >
          {(["csv", "json", "pdf"] as const).map((formato) => (
            <button
              type="button"
              key={formato}
              onClick={() => void exportar(formato)}
              className="block w-full rounded-lg px-4 py-2 text-left text-sm font-medium text-slate-700 hover:bg-cyan-50 focus-visible:bg-cyan-50"
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
