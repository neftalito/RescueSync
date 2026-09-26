import { type ReactElement, type ReactNode } from "react";

/** Aviso neutro de carga o de resultado vacío. */
export function Aviso({
  tono,
  children,
}: {
  tono: "neutro" | "error";
  children: ReactNode;
}): ReactElement {
  return tono === "error" ? (
    <section
      role="alert"
      className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm leading-6 text-red-800 shadow-sm"
    >
      {children}
    </section>
  ) : (
    <section
      role="status"
      className="rounded-2xl border border-slate-200 bg-white p-6 text-sm leading-6 text-slate-600 shadow-sm"
    >
      {children}
    </section>
  );
}

/** Error de consulta con opción de reintento, sin datos en pantalla. */
export function ErrorConReintento({
  mensaje,
  onReintentar,
}: {
  mensaje: string;
  onReintentar: () => void;
}): ReactElement {
  return (
    <Aviso tono="error">
      <p>{mensaje}</p>
      <button
        type="button"
        onClick={onReintentar}
        className="mt-4 rounded-xl border border-red-700 bg-white px-4 py-2.5 text-sm font-semibold text-red-900 transition hover:bg-red-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700"
      >
        Reintentar
      </button>
    </Aviso>
  );
}

/** Error al refrescar una consulta que ya tiene datos en pantalla. */
export function AvisoRefresco({
  mensaje,
  onReintentar,
}: {
  mensaje: string;
  onReintentar: () => void;
}): ReactElement {
  return (
    <section
      role="alert"
      className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-950"
    >
      <p>{mensaje} Seguimos mostrando los últimos datos disponibles.</p>
      <button
        type="button"
        onClick={onReintentar}
        className="mt-2 rounded-lg border border-amber-700 bg-white px-3 py-2 text-sm font-semibold text-amber-950 hover:bg-amber-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-700"
      >
        Reintentar actualización
      </button>
    </section>
  );
}
