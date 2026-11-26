export function porcentajeMonitoreo(valor: number | null): string {
  return valor === null ? "Sin datos" : `${valor.toLocaleString("es-AR", { maximumFractionDigits: 2 })} %`;
}

export function horasMonitoreo(valor: number | null): string {
  return valor === null ? "Sin datos" : `${(valor / 3600).toLocaleString("es-AR", { maximumFractionDigits: 3 })} h`;
}

export function etiquetaUmbral(horas: number): string {
  if (horas === 168) return "1 semana";
  if (horas === 720) return "1 mes (30 días)";
  return `${horas} h`;
}

