export type RGB = [number, number, number];
export type Tono = "info" | "aviso" | "ok" | "neutro";

// Paleta y medidas de página (A4, mm)
export const PRIMARIO: RGB = [14, 116, 144];
export const PRIMARIO_CLARO: RGB = [6, 182, 212];
export const TEXTO: RGB = [31, 41, 55];
export const GRIS: RGB = [107, 114, 128];
export const BORDE: RGB = [226, 232, 240];
export const FONDO_TARJETA: RGB = [244, 249, 251];
export const FILA_ALTERNA: RGB = [243, 248, 250];

export const TONOS: Record<Tono, { fondo: RGB; barra: RGB }> = {
  info: { fondo: [236, 254, 255], barra: PRIMARIO },
  aviso: { fondo: [254, 243, 199], barra: [217, 119, 6] },
  ok: { fondo: [220, 252, 231], barra: [22, 163, 74] },
  neutro: { fondo: [243, 244, 246], barra: GRIS },
};

export const PAGINA_ANCHO = 210;
export const MARGEN = 16;
export const ANCHO = PAGINA_ANCHO - MARGEN * 2; // 178
export const DERECHA = PAGINA_ANCHO - MARGEN; // 194
export const TOPE = 22; // y inicial en páginas internas
export const FONDO_UTIL = 278; // y máximo del contenido
