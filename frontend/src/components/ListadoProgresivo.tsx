import { useEffect, useRef, useState, type ReactElement, type ReactNode } from "react";
import type { UseInfiniteQueryResult } from "@tanstack/react-query";
import { TAMANO_PAGINA } from "../api/paginacion";

interface ScrollListadoProps {
  etiqueta: string;
  children: ReactNode;
  hayMas?: boolean;
  cargando?: boolean;
  error?: boolean;
  cargarMas?: () => void;
  className?: string;
}

/** Mantiene un scroll accesible con carga automática y alternativa por teclado. */
export function ScrollListado({
  etiqueta, children, hayMas = false, cargando = false, error = false,
  cargarMas, className = "",
}: ScrollListadoProps): ReactElement {
  const contenedor = useRef<HTMLDivElement>(null);
  const final = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!hayMas || cargando || error || !cargarMas || !final.current ||
      typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver((entradas) => {
      if (entradas.some((entrada) => entrada.isIntersecting)) cargarMas();
    }, { root: contenedor.current, rootMargin: "0px 0px 120px 0px" });
    observer.observe(final.current);
    return () => observer.disconnect();
  }, [hayMas, cargando, error, cargarMas]);

  return (
    <div
      ref={contenedor} role="region" aria-label={etiqueta} tabIndex={0}
      className={`min-h-0 min-w-0 max-h-[65dvh] overflow-auto overscroll-contain rounded-xl p-1 focus-visible:outline-2 focus-visible:outline-cyan-700 ${className}`}
    >
      {children}
      {hayMas && (
        <div ref={final} className="flex flex-col items-center gap-2 py-4">
          {error && <p role="alert" className="text-sm text-red-800">No pudimos cargar más registros. Podés reintentar.</p>}
          <button type="button" className="action-button" onClick={cargarMas} disabled={cargando}>
            {cargando ? "Cargando más…" : error ? "Reintentar carga" : "Cargar más"}
          </button>
          {cargando && <span role="status" className="sr-only">Cargando más registros</span>}
        </div>
      )}
    </div>
  );
}

export function ListadoRemoto<T>({ query, ...props }: {
  query: UseInfiniteQueryResult<T[], Error>;
  etiqueta: string;
  children: ReactNode;
  className?: string;
}): ReactElement {
  return <ScrollListado {...props} hayMas={query.hasNextPage}
    cargando={query.isFetching} error={query.isFetchNextPageError}
    cargarMas={() => { void query.fetchNextPage({ cancelRefetch: false }); }} />;
}

/** Recorta sólo la presentación de reportes que necesitan conservar datos completos. */
export function ListadoLocal<T>({ items, children, ...props }: {
  items: readonly T[];
  children: (visibles: readonly T[]) => ReactNode;
  etiqueta: string;
  className?: string;
}): ReactElement {
  const [cantidad, setCantidad] = useState(TAMANO_PAGINA);
  return <ScrollListado {...props} hayMas={cantidad < items.length}
    cargarMas={() => setCantidad((actual) => actual + TAMANO_PAGINA)}>
    {children(items.slice(0, cantidad))}
  </ScrollListado>;
}
