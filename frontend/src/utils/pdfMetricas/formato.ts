const TZ = "America/Argentina/Buenos_Aires";

export function formatearNumero(valor: unknown): string {
  const n = typeof valor === "number" ? valor : Number(valor);
  return Number.isFinite(n)
    ? n.toLocaleString("es-AR", { maximumFractionDigits: 3 })
    : String(valor);
}

export function formatearFecha(valor: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(valor);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : valor;
}

export function formatearFechaHora(valor: string): string {
  const fecha = new Date(valor);
  return Number.isNaN(fecha.getTime())
    ? valor
    : fecha.toLocaleString("es-AR", { timeZone: TZ });
}

export function formatearEtiquetaIndicador(clave: string): string {
  const texto = clave.replaceAll("_", " ");
  return (texto.charAt(0).toUpperCase() + texto.slice(1)).replace(
    /^Ong\b/,
    "ONG",
  );
}
