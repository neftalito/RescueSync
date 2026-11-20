import { type ReactElement, type ReactNode } from "react";

interface SelectorFiltroProps {
  etiqueta: string;
  valor: string;
  cambiar: (valor: string) => void;
  children: ReactNode;
}

export function SelectorFiltro({ etiqueta, valor, cambiar, children }: SelectorFiltroProps): ReactElement {
  return (
    <label className="block min-w-0 text-sm font-semibold text-slate-700">
      {etiqueta}
      <select className="form-input mt-2" value={valor} onChange={(event) => cambiar(event.target.value)}>
        {children}
      </select>
    </label>
  );
}
