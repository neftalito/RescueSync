export function porcentajeMonitoreo(valor: number | null): string {
  return valor === null ? "Sin datos" : `${valor.toLocaleString("es-AR", { maximumFractionDigits: 2 })} %`;
}

export function horasMonitoreo(valor: number | null): string {
  return valor === null ? "Sin datos" : `${(valor / 3600).toLocaleString("es-AR", { maximumFractionDigits: 3 })} h`;
}

