import { useState, type ReactElement } from "react";
import { useForm } from "react-hook-form";
import { milesimas, type LoteAdjudicado } from "../schemas/ejecucion";

interface CantidadFinalizada {
  loteId: number;
  movilizada: string;
  cumplida: string;
}

interface FormularioFinalizacion {
  cantidades: Array<{ movilizada: string; cumplida: string }>;
}

export function FormularioFinalizacionOng({
  lotes,
  pendiente,
  onFinalizar,
}: {
  lotes: LoteAdjudicado[];
  pendiente: boolean;
  onFinalizar: (cantidades: CantidadFinalizada[]) => void;
}): ReactElement {
  const [error, setError] = useState<string | null>(null);
  const { handleSubmit, register, setFocus } = useForm<FormularioFinalizacion>();

  function enviar(datos: FormularioFinalizacion): void {
    const cantidades: CantidadFinalizada[] = [];
    for (const [indice, lote] of lotes.entries()) {
      const entrada = datos.cantidades[indice];
      const movilizada = (entrada?.movilizada ?? "").trim().replace(",", ".");
      const cumplida = (entrada?.cumplida ?? "").trim().replace(",", ".");
      const movilizadaMilesimas = milesimas(movilizada);
      const cumplidaMilesimas = milesimas(cumplida);
      const maximo = milesimas(lote.cantidad);
      if (
        movilizadaMilesimas === null ||
        cumplidaMilesimas === null ||
        maximo === null ||
        cumplidaMilesimas > movilizadaMilesimas ||
        movilizadaMilesimas > maximo ||
        (!lote.admiteFracciones &&
          (movilizadaMilesimas % 1000n !== 0n || cumplidaMilesimas % 1000n !== 0n))
      ) {
        setError(`Revisá el lote ${lote.loteId}. La cantidad cumplida debe ser como máximo la movilizada y esta, como máximo la adjudicada. Usá ${lote.admiteFracciones ? "hasta tres decimales" : "cantidades enteras"}.`);
        setFocus(`cantidades.${indice}.movilizada`);
        return;
      }
      cantidades.push({ loteId: lote.loteId, movilizada, cumplida });
    }
    setError(null);
    onFinalizar(cantidades);
  }

  return (
    <form className="mt-3 space-y-3" onSubmit={handleSubmit(enviar)}>
      <p>Informá las cantidades reales de cada lote. Ingresá 0 cuando corresponda.</p>
      {lotes.map((lote, indice) => (
        <fieldset key={lote.loteId} className="grid min-w-0 gap-2 rounded-lg border border-slate-200 p-3 sm:grid-cols-2">
          <legend className="max-w-full break-words px-1 font-medium">
            Lote {lote.loteId} · {lote.capacidad} · {lote.cantidad} {lote.unidad} adjudicadas
          </legend>
          <label className="block min-w-0">
            Cantidad movilizada
            <input required inputMode="decimal" {...register(`cantidades.${indice}.movilizada`)} className="block w-full rounded border p-2" />
          </label>
          <label className="block min-w-0">
            Cantidad cumplida
            <input required inputMode="decimal" {...register(`cantidades.${indice}.cumplida`)} className="block w-full rounded border p-2" />
          </label>
        </fieldset>
      ))}
      {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
      <button className="action-button" disabled={pendiente}>Informar finalización</button>
    </form>
  );
}
