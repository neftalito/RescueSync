import { type ReactElement } from "react";

const LONGITUD_BUSQUEDA = 120;

interface CampoBusquedaProps {
  etiqueta: string;
  ejemplo?: string;
  valor: string;
  cambiar: (valor: string) => void;
}

export function CampoBusqueda({ etiqueta, ejemplo, valor, cambiar }: CampoBusquedaProps): ReactElement {
  return (
    <label className="block min-w-0 text-sm font-semibold text-slate-700">
      {etiqueta}
      <input
        type="search"
        className="form-input mt-2"
        placeholder={ejemplo}
        maxLength={LONGITUD_BUSQUEDA}
        value={valor}
        onChange={(event) => cambiar(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.preventDefault();
        }}
      />
    </label>
  );
}
