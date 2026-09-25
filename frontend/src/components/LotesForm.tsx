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
  /** Lotes persistidos: los borradores se editan y el resto se muestra fijo. */
  lotes: Lote[];
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
  lotes,
}: LotesFormProps): ReactElement {
  // El backend rechaza con 409 editar un lote que ya salió del borrador.
  const borradores = lotes.filter((lote) => lote.estado === "BORRADOR");
  const noEditables = lotes.filter((lote) => lote.estado !== "BORRADOR");
  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<LotesFormData>({
    resolver: zodResolver(lotesFormSchema),
    defaultValues: {
      lotes: borradores.length > 0 ? borradores.map(aFormulario) : [loteVacio],
    },
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
        onSuccess: (guardados) => {
          // Los lotes guardados vuelven con `id`: el próximo envío los edita.
          reset({ lotes: guardados.map(aFormulario) });
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
  const sinCambios = !isDirty && fields.every((field) => field.id !== null);

  return (
    <article className="w-full rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <p className="text-sm font-semibold text-cyan-800">Centro coordinador</p>
      <h2 className="mt-2 text-xl font-semibold text-slate-950">
        Lotes de necesidades
      </h2>
      <p className="mt-2 leading-7 text-slate-600">
        Desglosá la emergencia en lotes con tipo, cantidad y unidad. Los lotes
        se guardan en borrador y podés editarlos mientras no se publiquen:
        guardar no publica la convocatoria.
      </p>

      {noEditables.length > 0 && (
        <section aria-labelledby="lotes-no-editables" className="mt-6">
          <h3
            id="lotes-no-editables"
            className="text-sm font-semibold text-slate-900"
          >
            Lotes ya publicados
          </h3>
          <p className="mt-1 text-sm text-slate-500">
            Salieron del borrador y ya no admiten edición.
          </p>
          <ul className="mt-3 space-y-3">
            {noEditables.map((lote) => (
              <li
                key={lote.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm"
              >
                <div>
                  <p className="font-semibold text-slate-900">
                    {lote.tipo_necesidad}
                  </p>
                  <p className="mt-1 text-slate-600">
                    {lote.cantidad_requerida} {lote.unidad} · N.º {lote.id}
                  </p>
                </div>
                <span className="rounded-full bg-slate-200 px-3 py-1 text-xs font-semibold text-slate-700">
                  {estadoLoteLabels[lote.estado]}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

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
                  {loteId !== null && (
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                      {estadoLoteLabels.BORRADOR}
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
          disabled={mutation.isPending || sinCambios}
          className="flex w-full items-center justify-center rounded-xl bg-cyan-700 px-5 py-3.5 text-base font-bold text-white shadow-sm transition hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700 disabled:cursor-not-allowed disabled:opacity-70 aria-busy:cursor-wait"
          aria-busy={mutation.isPending}
        >
          {mutation.isPending
            ? "Guardando…"
            : sinCambios
              ? "Sin cambios para guardar"
              : "Guardar borrador"}
        </button>
      </form>
    </article>
  );
}
