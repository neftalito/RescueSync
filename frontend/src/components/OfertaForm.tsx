import { zodResolver } from "@hookform/resolvers/zod";
import { type ReactElement, useState } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";

import { ApiError } from "../api/client";
import { useConvocatoriasAbiertas } from "../hooks/useConvocatoriasAbiertas";
import { useRegistrarOferta } from "../hooks/useRegistrarOferta";
import type { LotePublicado } from "../schemas/convocatoria";
import {
  ofertaFormSchema,
  tipoAporteLabels,
  tiposAporte,
  type OfertaFormData,
} from "../schemas/oferta";

interface OfertaFormProps {
  csrfToken: string;
}

const inputClasses =
  "mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-base shadow-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100";

function formatoCantidad(cantidad: string): string {
  return new Intl.NumberFormat("es-AR", { maximumFractionDigits: 3 }).format(
    Number(cantidad),
  );
}

function nuevoItem(lote: LotePublicado): OfertaFormData["items"][number] {
  return {
    lote_id: lote.lote_id,
    tipo: "RECURSO",
    descripcion: lote.tipo_necesidad,
    cantidad_ofrecida: "",
    unidad: lote.unidad_publicada,
  };
}

export function OfertaForm({ csrfToken }: OfertaFormProps): ReactElement {
  const convocatoriasQuery = useConvocatoriasAbiertas();
  const mutation = useRegistrarOferta();
  const [loteParaAgregar, setLoteParaAgregar] = useState("");
  const {
    control,
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<OfertaFormData>({
    resolver: zodResolver(ofertaFormSchema),
    defaultValues: { convocatoria_id: 0, observaciones: "", items: [] },
  });
  const { fields, append, remove, replace } = useFieldArray({
    control,
    name: "items",
  });
  const convocatoriaId = useWatch({ control, name: "convocatoria_id" });
  const items = useWatch({ control, name: "items" }) ?? [];
  const convocatorias = convocatoriasQuery.data ?? [];
  const convocatoria = convocatorias.find((item) => item.id === convocatoriaId);
  const lotes = convocatoria?.lotes ?? [];
  const lotesAgregados = new Set(items.map((item) => item.lote_id));
  const lotesSinAgregar = lotes.filter(
    (lote) => !lotesAgregados.has(lote.lote_id),
  );
  const requestError =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.isError
        ? "No pudimos presentar la oferta. Intentá nuevamente."
        : null;
  const itemsError = errors.items?.root?.message ?? errors.items?.message;

  const cambiarConvocatoria = (): void => {
    replace([]);
    setLoteParaAgregar("");
    mutation.reset();
  };

  const agregarLote = (): void => {
    const lote = lotes.find((opcion) => opcion.lote_id === Number(loteParaAgregar));
    if (lote === undefined || lotesAgregados.has(lote.lote_id)) return;
    append(nuevoItem(lote));
    setLoteParaAgregar("");
  };

  const presentar = (datos: OfertaFormData): void => {
    mutation.mutate({ datos, csrfToken });
  };

  const presentarOtra = (): void => {
    mutation.reset();
    reset({ convocatoria_id: convocatoriaId, observaciones: "", items: [] });
  };

  // La confirmación de una escritura ya completada tiene prioridad sobre la
  // recarga de consultas invalidada por la mutación. La convocatoria puede
  // vencer entre ambas respuestas sin que eso invalide la oferta creada.
  if (mutation.isSuccess) {
    return (
      <article className="w-full max-w-3xl rounded-2xl border border-green-200 bg-white p-6 shadow-sm sm:p-8">
        <div
          role="status"
          className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm leading-6 text-green-900"
        >
          <p className="font-semibold">
            Oferta {mutation.data.id} presentada correctamente.
          </p>
          <p className="mt-1">
            Se registraron {mutation.data.items.length} lotes en estado{" "}
            {mutation.data.estado}.
          </p>
        </div>
        <button
          type="button"
          onClick={presentarOtra}
          className="mt-5 rounded-xl bg-cyan-700 px-5 py-3 text-sm font-bold text-white hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700"
        >
          Presentar otra oferta
        </button>
      </article>
    );
  }

  if (convocatoriasQuery.isPending) {
    return (
      <article className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <p role="status" className="text-sm text-slate-600">
          Cargando convocatorias disponibles…
        </p>
      </article>
    );
  }

  if (convocatoriasQuery.isError) {
    return (
      <article className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <p role="alert" className="text-sm leading-6 text-red-800">
          {convocatoriasQuery.error instanceof ApiError
            ? convocatoriasQuery.error.message
            : "No pudimos cargar las convocatorias. Intentá nuevamente."}
        </p>
        <button
          type="button"
          onClick={() => void convocatoriasQuery.refetch()}
          className="mt-4 rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700"
        >
          Reintentar
        </button>
      </article>
    );
  }

  if (convocatorias.length === 0) {
    return (
      <article className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <p role="status" className="text-sm leading-6 text-slate-600">
          En este momento no hay convocatorias abiertas para ofertar.
        </p>
      </article>
    );
  }

  return (
    <article className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <p className="text-sm font-semibold text-cyan-800">Representante de ONG</p>
      <h2 className="mt-2 text-2xl font-semibold text-slate-950">
        Presentar oferta
      </h2>
      <p className="mt-2 leading-7 text-slate-600">
        Elegí una convocatoria y ofrecé recursos, personal o ambos para uno o más
        lotes. Podés cubrir solo una parte de la cantidad publicada.
      </p>

      <form
        className="mt-6 space-y-6"
        onSubmit={(event) => void handleSubmit(presentar)(event)}
        noValidate
      >
        <div>
          <label
            htmlFor="convocatoria_id"
            className="block text-sm font-semibold text-slate-800"
          >
            Convocatoria
          </label>
          <select
            id="convocatoria_id"
            aria-invalid={errors.convocatoria_id !== undefined}
            aria-describedby={
              errors.convocatoria_id ? "convocatoria-error" : undefined
            }
            className={inputClasses}
            {...register("convocatoria_id", {
              valueAsNumber: true,
              onChange: cambiarConvocatoria,
            })}
          >
            <option value={0}>Seleccioná una convocatoria</option>
            {convocatorias.map((opcion) => (
              <option key={opcion.id} value={opcion.id}>
                Emergencia {opcion.emergencia_id} · {opcion.emergencia.zona} ·
                Convocatoria {opcion.numero}
              </option>
            ))}
          </select>
          {errors.convocatoria_id && (
            <p id="convocatoria-error" className="mt-2 text-sm text-red-700">
              {errors.convocatoria_id.message}
            </p>
          )}
        </div>

        {convocatoria && (
          <section
            aria-labelledby="lotes-heading"
            className="rounded-2xl border border-slate-200 bg-slate-50 p-4 sm:p-5"
          >
            <h3 id="lotes-heading" className="font-semibold text-slate-950">
              Lotes publicados · {convocatoria.emergencia.zona}
            </h3>
            <div className="mt-4 flex flex-col gap-3 sm:flex-row">
              <div className="min-w-0 flex-1">
                <label
                  htmlFor="lote-para-agregar"
                  className="block text-sm font-semibold text-slate-800"
                >
                  Lote para agregar
                </label>
                <select
                  id="lote-para-agregar"
                  value={loteParaAgregar}
                  onChange={(event) => setLoteParaAgregar(event.target.value)}
                  className={inputClasses}
                  disabled={lotesSinAgregar.length === 0}
                >
                  <option value="">Seleccioná un lote</option>
                  {lotesSinAgregar.map((lote) => (
                    <option key={lote.lote_id} value={lote.lote_id}>
                      {lote.tipo_necesidad} · hasta{" "}
                      {formatoCantidad(lote.cantidad_publicada)}{" "}
                      {lote.unidad_publicada}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="button"
                onClick={agregarLote}
                disabled={loteParaAgregar === ""}
                className="mt-2 rounded-xl border border-cyan-700 px-4 py-3 text-sm font-semibold text-cyan-800 hover:bg-cyan-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700 disabled:cursor-not-allowed disabled:opacity-50 sm:mt-7"
              >
                Agregar lote
              </button>
            </div>

            {itemsError && (
              <p role="alert" className="mt-3 text-sm text-red-700">
                {itemsError}
              </p>
            )}

            <div className="mt-5 space-y-4">
              {fields.map((field, index) => {
                const lote = lotes.find(
                  (opcion) => opcion.lote_id === items[index]?.lote_id,
                );
                const itemErrors = errors.items?.[index];
                return (
                  <fieldset
                    key={field.id}
                    className="rounded-xl border border-slate-200 bg-white p-4"
                  >
                    <legend className="px-1 text-sm font-semibold text-slate-900">
                      {lote?.tipo_necesidad ?? `Lote ${index + 1}`}
                    </legend>
                    {lote && (
                      <p className="mb-4 text-sm text-slate-600">
                        Publicado: {formatoCantidad(lote.cantidad_publicada)}{" "}
                        {lote.unidad_publicada}
                      </p>
                    )}
                    <input
                      type="hidden"
                      {...register(`items.${index}.lote_id`, {
                        valueAsNumber: true,
                      })}
                    />
                    <input
                      type="hidden"
                      {...register(`items.${index}.unidad`)}
                    />

                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <label
                          htmlFor={`items.${index}.tipo`}
                          className="block text-sm font-semibold text-slate-800"
                        >
                          Tipo de aporte
                        </label>
                        <select
                          id={`items.${index}.tipo`}
                          className={inputClasses}
                          {...register(`items.${index}.tipo`)}
                        >
                          {tiposAporte.map((tipo) => (
                            <option key={tipo} value={tipo}>
                              {tipoAporteLabels[tipo]}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label
                          htmlFor={`items.${index}.cantidad_ofrecida`}
                          className="block text-sm font-semibold text-slate-800"
                        >
                          Cantidad ofrecida
                        </label>
                        <div className="flex items-center gap-2">
                          <input
                            id={`items.${index}.cantidad_ofrecida`}
                            type="text"
                            inputMode="decimal"
                            aria-invalid={itemErrors?.cantidad_ofrecida !== undefined}
                            aria-describedby={
                              itemErrors?.cantidad_ofrecida
                                ? `cantidad-${index}-error`
                                : undefined
                            }
                            className={inputClasses}
                            {...register(`items.${index}.cantidad_ofrecida`)}
                          />
                          <span className="mt-2 shrink-0 text-sm text-slate-600">
                            {lote?.unidad_publicada}
                          </span>
                        </div>
                        {itemErrors?.cantidad_ofrecida && (
                          <p
                            id={`cantidad-${index}-error`}
                            className="mt-2 text-sm text-red-700"
                          >
                            {itemErrors.cantidad_ofrecida.message}
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="mt-4">
                      <label
                        htmlFor={`items.${index}.descripcion`}
                        className="block text-sm font-semibold text-slate-800"
                      >
                        Descripción del aporte
                      </label>
                      <input
                        id={`items.${index}.descripcion`}
                        type="text"
                        maxLength={2000}
                        aria-invalid={itemErrors?.descripcion !== undefined}
                        aria-describedby={
                          itemErrors?.descripcion
                            ? `descripcion-${index}-error`
                            : undefined
                        }
                        className={inputClasses}
                        {...register(`items.${index}.descripcion`)}
                      />
                      {itemErrors?.descripcion && (
                        <p
                          id={`descripcion-${index}-error`}
                          className="mt-2 text-sm text-red-700"
                        >
                          {itemErrors.descripcion.message}
                        </p>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => remove(index)}
                      className="mt-4 rounded-lg px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700"
                    >
                      Quitar lote
                    </button>
                  </fieldset>
                );
              })}
            </div>
          </section>
        )}

        <div>
          <label
            htmlFor="observaciones"
            className="block text-sm font-semibold text-slate-800"
          >
            Observaciones (opcional)
          </label>
          <textarea
            id="observaciones"
            rows={3}
            aria-invalid={errors.observaciones !== undefined}
            aria-describedby={
              errors.observaciones ? "observaciones-error" : undefined
            }
            className={`${inputClasses} resize-y`}
            {...register("observaciones")}
          />
          {errors.observaciones && (
            <p id="observaciones-error" className="mt-2 text-sm text-red-700">
              {errors.observaciones.message}
            </p>
          )}
        </div>

        {requestError && (
          <p
            role="alert"
            className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800"
          >
            {requestError}
          </p>
        )}

        <button
          type="submit"
          disabled={mutation.isPending}
          className="flex w-full items-center justify-center rounded-xl bg-cyan-700 px-5 py-3.5 text-base font-bold text-white shadow-sm transition hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700 disabled:cursor-wait disabled:opacity-70"
        >
          {mutation.isPending ? "Presentando oferta…" : "Presentar oferta"}
        </button>
      </form>
    </article>
  );
}
