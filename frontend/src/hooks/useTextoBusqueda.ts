import { useEffect, useState } from "react";

export function useTextoBusqueda(): {
  texto: string;
  cambiar: (texto: string) => void;
  termino: string;
} {
  const [texto, setTexto] = useState("");
  const [termino, setTermino] = useState("");
  const textoLimpio = texto.trim();

  useEffect(() => {
    if (!textoLimpio) return;
    const espera = window.setTimeout(() => setTermino(textoLimpio), 250);
    return () => window.clearTimeout(espera);
  }, [textoLimpio]);

  function cambiar(valor: string): void {
    setTexto(valor);
    if (!valor.trim()) setTermino("");
  }

  return { texto, cambiar, termino };
}
