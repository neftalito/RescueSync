/** Formatea una marca de tiempo de la API en la zona horaria del navegador. */
export function formatearFecha(iso: string): string {
  return new Date(iso).toLocaleString("es-AR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
