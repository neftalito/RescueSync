import { useFieldArray, type Control, type FieldErrors, type UseFormRegister } from "react-hook-form";
import type { ReactElement } from "react";
import type { OfertaFormData } from "../schemas/oferta";
import type { Recurso } from "../schemas/inventario";
interface Props {
    index: number;
    control: Control<OfertaFormData>;
    register: UseFormRegister<OfertaFormData>;
    errores: FieldErrors<OfertaFormData>;
    recursos: Recurso[];
}
export function RecursosOferta({ index, control, register, errores, recursos }: Props): ReactElement {
    const { fields, append, remove } = useFieldArray({ control, name: `items.${index}.aportes` });
    const error = errores.items?.[index]?.aportes;
    return <div className="mt-4 rounded-xl border border-cyan-200 bg-cyan-50 p-4">
    <p className="font-semibold">Recursos de mi ONG</p>
    <p className="mt-1 text-sm">Desglosá la cantidad ofrecida. La disponibilidad se volverá a comprobar al adjudicar.</p>
    {fields.map((field, aporteIndex) => <div key={field.id} className="mt-3 grid gap-2 sm:grid-cols-3">
      <label>Recurso
        <select className="mt-1 w-full rounded border border-slate-300 bg-white p-2" {...register(`items.${index}.aportes.${aporteIndex}.recurso_nacional_id`)}>
          <option value="">Elegí un recurso</option>
          {recursos.map((r) => <option key={r.id} value={r.id}>{r.nombre} · {r.cantidadDisponible} {r.unidad} disponibles</option>)}
        </select>
      </label>
      <label>Cantidad del recurso
        <input className="mt-1 w-full rounded border border-slate-300 bg-white p-2" inputMode="decimal" {...register(`items.${index}.aportes.${aporteIndex}.cantidad`)}/>
      </label>
      <button type="button" className="self-end rounded border border-slate-300 p-2" onClick={() => remove(aporteIndex)}>Quitar recurso</button>
      {error?.[aporteIndex]?.recurso_nacional_id && <p role="alert">{error[aporteIndex].recurso_nacional_id.message}</p>}
      {error?.[aporteIndex]?.cantidad && <p role="alert">{error[aporteIndex].cantidad.message}</p>}
    </div>)}
    <button type="button" className="mt-3 rounded border border-cyan-700 bg-white px-3 py-2" onClick={() => append({ recurso_nacional_id: "", cantidad: "" })}>Agregar recurso</button>
    {recursos.length === 0 && <p className="mt-2 text-sm">No hay recursos compatibles. Revisá tu inventario nacional.</p>}
    {(error?.message || error?.root?.message) && <p role="alert" className="mt-2 text-red-800">{error.message ?? error.root?.message}</p>}
  </div>;
}
