/** Normaliza las vocales acentuadas y conserva letras como la ñ. */
export function normalizarBusqueda(texto: string): string {
  return texto.trim().toLowerCase().normalize("NFD")
    .replace(/([aeiou])\u0301/g, "$1")
    .replace(/u\u0308/g, "u")
    .normalize("NFC");
}
