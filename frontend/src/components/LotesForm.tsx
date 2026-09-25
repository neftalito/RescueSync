import { zodResolver } from "@hookform/resolvers/zod";
import { type ReactElement } from "react";
import { useFieldArray, useForm } from "react-hook-form";

import { ApiError } from "../api/client";
import { useGuardarLotes } from "../hooks/useGuardarLotes";
import {
  estadoLoteLabels,
  lotesFormSchema,
  type Lote,
  type LoteItemFormData,
  type LotesFormData,
} from "../schemas/lote";

interface LotesFormProps {
  emergenciaId: number;
  csrfToken: string;
}

const inputClasses =
  "mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3.5 text-base shadow-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100";

const loteVacio: LoteItemFormData = {
  id: null,
  tipo_necesidad: "",
  cantidad_requerida: "",
  unidad: "",
  descripcion: "",
};

function aFormulario(lote: Lote): LoteItemFormData {
  return {
    id: lote.id,
    tipo_necesidad: lote.tipo_necesidad,
    cantidad_requerida: lote.cantidad_requerida,
    unidad: lote.unidad,
    descripcion: lote.descripcion ?? "",
  };
}

export function LotesForm({
  emergenciaId,
  csrfToken,
}: LotesFormProps): ReactElement {
  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<LotesFormData>({
    resolver: zodResolver(lotesFormSchema),
    defaultValues: { lotes: [loteVacio] },
  });
  const { fields, append, remove } = useFieldArray({
    control,
    name: "lotes",
    // `id` pertenece al lote persistido; RHF usa otra clave para sus filas.
    keyName: "clave",
  });
  const mutation = useGuardarLotes(emergenciaId);

  const submit = (datos: LotesFormData): void => {
    mutation.mutate(
      { ...datos, csrfToken },
      {
        onSuccess: (lotes) => {
          // Los lotes guardados vuelven con `id`: el próximo envío los edita.
          reset({ lotes: lotes.map(aFormulario) });
        },
      },
    );
  };
  const requestError =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.isError
        ? "No pudimos guardar los lotes. Intentá nuevamente."
        : null;
  const guardados = mutation.isSuccess ? mutation.data : [];
  const estadoPorId = new Map(guardados.map((lote) => [lote.id, lote.estado]));

  return (
    <article className="w-full rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <p className="text-sm font-semibold text-cyan-800">Centro coordinador</p>
      <h2 className="mt-2 text-xl font-semibold text-slate-950">
        Lotes de necesidades
      </h2>
      <p className="mt-2 leading-7 text-slate-600">
        Desglosá la emergencia en lotes con tipo, cantidad y unidad. Los lotes
        se guardan en borrador: guardar no publica la convocatoria.
      </p>

      <form
        className="mt-6 space-y-6"
        onSubmit={(event) => void handleSubmit(submit)(event)}
        noValidate
      >
        <ol className="space-y-5">
          {fields.map((field, index) => {
            const erroresLote = errors.lotes?.[index];
            const prefijo = `lote-${index}`;
            const loteId = field.id;
            const estado = loteId === null ? undefined : estadoPorId.get(loteId);
            const describedBy = (campo: string, conError: boolean): string | undefined =>
              conError ? `${prefijo}-${campo}-error` : undefined;

            return (
              <li key={field.clave}>
                <fieldset className="rounded-2xl border border-slate-200 p-5">
                  <legend className="px-2 text-sm font-semibold text-slate-900">
                    Lote {index + 1}
                    {loteId !== null && (
                      <span className="ml-2 font-normal text-slate-500">
                        · N.º {loteId}
                      </span>
                    )}
                  </legend>
                  {estado && (
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                      {estadoLoteLabels[estado]}
                    </span>
                  )}

                  <div className="mt-2 grid gap-5 sm:grid-cols-2">
                    <div className="sm:col-span-2">
                      <label
                        htmlFor={`${prefijo}-tipo`}
                        className="block text-sm font-semibold text-slate-800"
                      >
                        Tipo de necesidad
                      </label>
                      <input
                        id={`${prefijo}-tipo`}
                        type="text"
                        autoComplete="off"
                        aria-invalid={erroresLote?.tipo_necesidad !== undefined}
                        aria-describedby={describedBy(
                          "tipo",
                          erroresLote?.tipo_necesidad !== undefined,
                        )}
                        className={inputClasses}
                        placeholder="Agua potable, colchones, voluntarios…"
                        {...register(`lotes.${index}.tipo_necesidad`)}
                      />
                      {erroresLote?.tipo_necesidad && (
                        <p
                          id={`${prefijo}-tipo-error`}
                          className="mt-2 text-sm text-red-700"
                        >
                          {erroresLote.tipo_necesidad.message}
                        </p>
                      )}
                    </div>

                    <div>
                      <label
                        htmlFor={`${prefijo}-cantidad`}
                        className="block text-sm font-semibold text-slate-800"
                      >
                        Cantidad requerida
                      </label>
                      <input
                        id={`${prefijo}-cantidad`}
                        type="text"
                        inputMode="decimal"
                        autoComplete="off"
                        aria-invalid={
                          erroresLote?.cantidad_requerida !== undefined
                        }
                        aria-describedby={describedBy(
                          "cantidad",
                          erroresLote?.cantidad_requerida !== undefined,
                        )}
                        className={inputClasses}
                        placeholder="500"
                        {...register(`lotes.${index}.cantidad_requerida`)}
                      />
                      {erroresLote?.cantidad_requerida && (
                        <p
                          id={`${prefijo}-cantidad-error`}
                          className="mt-2 text-sm text-red-700"
                        >
                          {erroresLote.cantidad_requerida.message}
                        </p>
                      )}
                    </div>

                    <div>
                      <label
                        htmlFor={`${prefijo}-unidad`}
                        className="block text-sm font-semibold text-slate-800"
                      >
                        Unidad
                      </label>
                      <input
                        id={`${prefijo}-unidad`}
                        type="text"
                        autoComplete="off"
                        aria-invalid={erroresLote?.unidad !== undefined}
                        aria-describedby={describedBy(
                          "unidad",
                          erroresLote?.unidad !== undefined,
                        )}
                        className={inputClasses}
                        placeholder="litros, unidades, personas…"
                        {...register(`lotes.${index}.unidad`)}
                      />
                      {erroresLote?.unidad && (
                        <p
                          id={`${prefijo}-unidad-error`}
                          className="mt-2 text-sm text-red-700"
                        >
                          {erroresLote.unidad.message}
                        </p>
                      )}
                    </div>

                    <div className="sm:col-span-2">
                      <label
                        htmlFor={`${prefijo}-descripcion`}
                        className="block text-sm font-semibold text-slate-800"
                      >
                        Descripción (opcional)
                      </label>
                      <textarea
                        id={`${prefijo}-descripcion`}
                        rows={2}
                        aria-invalid={erroresLote?.descripcion !== undefined}
                        aria-describedby={describedBy(
                          "descripcion",
                          erroresLote?.descripcion !== undefined,
                        )}
                        className={`${inputClasses} min-h-20 resize-y`}
                        placeholder="Especificaciones, prioridad o punto de entrega"
                        {...register(`lotes.${index}.descripcion`)}
                      />
                      {erroresLote?.descripcion && (
                        <p
                          id={`${prefijo}-descripcion-error`}
                          className="mt-2 text-sm text-red-700"
                        >
                          {erroresLote.descripcion.message}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* La API no elimina lotes: solo se quitan filas sin guardar. */}
                  {loteId === null && fields.length > 1 && (
                    <button
                      type="button"
                      onClick={() => remove(index)}
                      className="mt-5 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700"
                    >
                      Quitar lote {index + 1}
                    </button>
                  )}
                </fieldset>
              </li>
            );
          })}
        </ol>

        {errors.lotes?.root && (
          <p role="alert" className="text-sm text-red-700">
            {errors.lotes.root.message}
          </p>
        )}

        <button
          type="button"
          onClick={() => append(loteVacio)}
          className="w-full rounded-xl border border-cyan-700 bg-white px-4 py-2.5 text-sm font-semibold text-cyan-800 transition hover:bg-cyan-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700 sm:w-auto"
        >
          Agregar lote
        </button>

        {mutation.isSuccess && !isDirty && (
          <div
            role="status"
            className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm leading-6 text-green-900"
          >
            <p className="font-semibold">
              {guardados.length === 1
                ? "1 lote guardado en borrador."
                : `${guardados.length} lotes guardados en borrador.`}
            </p>
            <p className="mt-1">
              La convocatoria todavía no se publicó. Podés seguir editando los
              lotes antes de publicarla.
            </p>
          </div>
        )}

        {requestError && (
          <div
            role="alert"
            className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800"
          >
            {requestError}
          </div>
        )}

        <button
          type="submit"
          disabled={mutation.isPending}
          className="flex w-full items-center justify-center rounded-xl bg-cyan-700 px-5 py-3.5 text-base font-bold text-white shadow-sm transition hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700 disabled:cursor-wait disabled:opacity-70"
        >
          {mutation.isPending ? "Guardando…" : "Guardar borrador"}
        </button>
      </form>
    </article>
  );
}
