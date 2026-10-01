const formateadorCantidad = new Intl.NumberFormat("es-AR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const formateadorCantidadParaFormulario = new Intl.NumberFormat("es-AR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
  useGrouping: false,
});

/** Muestra una cantidad con separadores argentinos y dos cifras decimales. */
export function formatearCantidad(cantidad: string | number): string {
  return formateadorCantidad.format(Number(cantidad));
}

/** Prepara una cantidad para un campo decimal sin agregar separadores de miles. */
export function formatearCantidadParaFormulario(cantidad: string | number): string {
  return formateadorCantidadParaFormulario.format(Number(cantidad));
}
