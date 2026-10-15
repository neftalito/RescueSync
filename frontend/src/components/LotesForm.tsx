import { ListadoLocal, ScrollListado } from "./ListadoProgresivo";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useState, type ReactElement } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { ActionIcon } from "./ActionIcon";
import { ApiError, apiRequest } from "../api/client";
import { capacidadSchema } from "../schemas/inventario";
import { gravedades, gravedadLabels } from "../schemas/emergencia";
import { useEliminarLote } from "../hooks/useEliminarLote";
import { useGuardarLotes } from "../hooks/useGuardarLotes";
import { usePublicarConvocatoria } from "../hooks/usePublicarConvocatoria";
import {
  estadoLoteLabels,
  lotesFormSchema,
  type Lote,
  type LoteItemFormData,
  type LotesFormData,
} from "../schemas/lote";
import {
  formatearCantidad,
  formatearCantidadParaFormulario,
} from "../utils/cantidades";

interface LotesFormProps {
  emergenciaId: number;
  csrfToken: string;
  convocatoriaPublicada: boolean;
  soloLectura?: boolean;
  /** Lotes persistidos: los borradores se editan y el resto se muestra fijo. */
  lotes: Lote[];
}

const inputClasses =
  "mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3.5 text-base shadow-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100";

const loteVacio: LoteItemFormData = {
  id: null,
  version: null,
  tipo_necesidad: "",
  cantidad_requerida: "",
  unidad: "",
  descripcion: "",
  capacidad_nacional_id: "",
  riesgo_requerido: "",
};

function aFormulario(lote: Lote): LoteItemFormData {
  return {
    id: lote.id,
    version: lote.version,
    tipo_necesidad: lote.tipo_necesidad,
    cantidad_requerida: formatearCantidadParaFormulario(
      lote.cantidad_requerida,
    ),
    unidad: lote.unidad,
    descripcion: lote.descripcion ?? "",
    capacidad_nacional_id: lote.capacidad_nacional_id ?? "",
    riesgo_requerido: lote.riesgo_requerido ?? "",
  };
}

export function LotesForm({
  emergenciaId,
  csrfToken,
  convocatoriaPublicada,
  soloLectura = false,
  lotes,
}: LotesFormProps): ReactElement {
  // El backend rechaza con 409 editar un lote que ya salió del borrador.
  const borradores = soloLectura
    ? []
    : lotes.filter((lote) => lote.estado === "BORRADOR");
  const noEditables = soloLectura
    ? lotes
    : lotes.filter((lote) => lote.estado !== "BORRADOR");
  const {
    register,
    control,
    handleSubmit,
    reset,
    getValues,
    setValue,
    setError,
    formState: { errors, isDirty, defaultValues },
  } = useForm<LotesFormData>({
    resolver: zodResolver(lotesFormSchema),
    defaultValues: {
      lotes: borradores.length > 0 ? borradores.map(aFormulario) : [loteVacio],
    },
  });
  const { fields, append, remove, replace } = useFieldArray({
    control,
    name: "lotes",
    // `id` pertenece al lote persistido; RHF usa otra clave para sus filas.
    keyName: "clave",
  });
  const valores = useWatch({ control, name: "lotes" });
  const mutation = useGuardarLotes(emergenciaId);
  const eliminacion = useEliminarLote(emergenciaId);
  const publicacion = usePublicarConvocatoria(emergenciaId);
  // Borrador cuya eliminación espera confirmación: es estado de la interfaz,
  // no un valor del formulario.
  const [confirmando, setConfirmando] = useState<number | null>(null);
  const catalogo = useQuery({
    enabled: !soloLectura,
    queryKey: ["capacidades-coordinacion"],
    queryFn: () =>
      apiRequest(
        "/emergencias/catalogos/capacidades-nacionales",
        z.array(capacidadSchema),
      ),
    retry: false,
  });
  const catalogoDisponible = catalogo.isSuccess && catalogo.data.length > 0;

  const submit = (datos: LotesFormData): void => {
    // Revalidar contra el catálogo cargado evita enviar nombres o unidades
    // anteriores al editar un borrador o al refrescar las capacidades.
    const lotesConCapacidad = datos.lotes.flatMap((lote, index) => {
      const capacidad = catalogo.data?.find(
        (item) => item.id === lote.capacidad_nacional_id,
      );
      if (!capacidad) {
        setError(`lotes.${index}.capacidad_nacional_id`, {
          message: "Seleccioná una capacidad disponible en el catálogo.",
        });
        return [];
      }
      return [{
        ...lote,
        tipo_necesidad: capacidad.nombre,
        unidad: capacidad.unidad,
      }];
    });
    if (lotesConCapacidad.length !== datos.lotes.length) return;
    eliminacion.reset();
    publicacion.reset();
    mutation.mutate(
      {
        lotes: lotesConCapacidad,
        csrfToken,
      },
      {
        onSuccess: (guardados) => {
          // Los lotes guardados vuelven con `id`: el próximo envío los edita.
          reset({ lotes: guardados.map(aFormulario) });
        },
      },
    );
  };
  const eliminarGuardado = (loteId: number): void => {
    mutation.reset();
    publicacion.reset();
    eliminacion.mutate(
      { loteId, csrfToken },
      {
        onSuccess: () => {
          setConfirmando(null);
          const sinLote = <T extends { id?: number | null; } | undefined>(
            items: T[],
          ): T[] => items.filter((item) => item?.id !== loteId);
          const actuales = sinLote(getValues("lotes"));
          // El lote ya no existe en la base: se quita también de los valores
          // iniciales para que las ediciones sin guardar de otras filas sigan
          // contando como cambios pendientes.
          reset({ lotes: sinLote(defaultValues?.lotes ?? []) });
          replace(actuales.length > 0 ? actuales : [loteVacio]);
        },
      },
    );
  };
  const ocupado =
    mutation.isPending || eliminacion.isPending || publicacion.isPending;
  const bloqueado = ocupado || publicacion.isSuccess;
  const requestError =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.isError
        ? "No pudimos guardar los lotes. Intentá nuevamente."
        : null;
  const guardados = mutation.isSuccess ? mutation.data : [];
  const sinCambios = !isDirty && fields.every((field) => field.id !== null);
  const puedePublicar =
    !isDirty &&
    fields.length > 0 &&
    fields.every((field) => field.id !== null);
  const eliminacionError =
    eliminacion.error instanceof ApiError
      ? eliminacion.error.message
      : eliminacion.isError
        ? "No pudimos eliminar el lote. Intentá nuevamente."
        : null;
  const publicacionError =
    publicacion.error instanceof ApiError
      ? publicacion.error.message
      : publicacion.isError
        ? "No pudimos publicar la convocatoria. Intentá nuevamente."
        : null;

  return (
    <article className="w-full rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <p className="text-sm font-semibold text-cyan-800">Centro coordinador</p>
      <h2 className="mt-2 text-xl font-semibold text-slate-950">
        Lotes de necesidades
      </h2>
      <p className="mt-2 leading-7 text-slate-600">
        {soloLectura ? (
          "La emergencia ya no admite editar lotes. Podés consultar sus necesidades y el estado de cada lote."
        ) : (
          <>
            Elegí una capacidad del catálogo nacional e indicá la cantidad requerida.
            La unidad se determina automáticamente. Los lotes se guardan en borrador
            y podés editarlos o eliminarlos mientras no se publiquen: guardar no
            publica la convocatoria.
          </>
        )}
      </p>

      {noEditables.length > 0 && (
        <section aria-labelledby="lotes-no-editables" className="mt-6">
          <h3
            id="lotes-no-editables"
            className="text-sm font-semibold text-slate-900"
          >
            {soloLectura ? "Lotes registrados" : "Lotes ya publicados"}
          </h3>
          <p className="mt-1 text-sm text-slate-500">
            {soloLectura
              ? "Consulta de los lotes creados para esta emergencia."
              : "Salieron del borrador y ya no admiten edición."}
          </p>
          <ListadoLocal items={noEditables} etiqueta="Lotes registrados" className="mt-3">
            {(visibles) => (
              <ul className="mt-3 space-y-3">
                {visibles.map((lote) => (
                  <li
                    key={lote.id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm"
                  >
                    <div>
                      <p className="font-semibold text-slate-900">
                        {lote.tipo_necesidad}
                      </p>
                      <p className="mt-1 text-slate-600">
                        {formatearCantidad(lote.cantidad_requerida)} {lote.unidad} ·
                        N.º {lote.id}
                      </p>
                    </div>
                    <span className="rounded-full bg-slate-200 px-3 py-1 text-xs font-semibold text-slate-700">
                      {estadoLoteLabels[lote.estado]}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </ListadoLocal>
        </section>
      )}

      {!soloLectura && (
        <form
          className="mt-6 space-y-6"
          onSubmit={(event) => void handleSubmit(submit)(event)}
          noValidate
          aria-busy={ocupado}
        >
          {catalogo.isPending && <p role="status">Cargando capacidades…</p>}
          {catalogo.isError && (
            <div role="alert" className="rounded-xl bg-red-50 p-4 text-red-800">
              <p>
                {catalogo.error instanceof ApiError
                  ? catalogo.error.message
                  : "No pudimos consultar las capacidades."}
              </p>
              <button
                type="button"
                disabled={catalogo.isFetching}
                onClick={() => void catalogo.refetch()}
                className="action-button action-icon mt-2"
                title="Reintentar catálogo"
              >
                <ActionIcon name="refresh" />
                <span className="sr-only">Reintentar catálogo</span>
              </button>
            </div>
          )}
          {catalogo.isSuccess && catalogo.data.length === 0 && (
            <p role="status" className="rounded-xl bg-amber-50 p-4 text-amber-900">
              El catálogo nacional todavía no tiene capacidades activas.
            </p>
          )}
          <ScrollListado etiqueta="Edición de lotes">
            <ol className="space-y-5">
              {fields.map((field, index) => {
                const erroresLote = errors.lotes?.[index];
                const prefijo = `lote-${index}`;
                const loteId = field.id;
                const capacidadId = valores[index]?.capacidad_nacional_id ?? "";
                const capacidadSeleccionada = catalogo.data?.find(
                  (item) => item.id === capacidadId,
                );
                const describedBy = (campo: string, conError: boolean): string | undefined =>
                  conError ? `${prefijo}-${campo}-error` : undefined;

                return (
                  <li key={field.clave}>
                    <fieldset
                      disabled={bloqueado}
                      className="rounded-2xl border border-slate-200 p-5 disabled:cursor-wait disabled:opacity-70"
                    >
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
                            htmlFor={`${prefijo}-capacidad`}
                            className="block text-sm font-semibold text-slate-800"
                          >
                            Capacidad
                          </label>
                          <select
                            id={`${prefijo}-capacidad`}
                            value={capacidadId}
                            disabled={!catalogoDisponible}
                            aria-invalid={
                              erroresLote?.capacidad_nacional_id !== undefined
                            }
                            aria-describedby={describedBy(
                              "capacidad",
                              erroresLote?.capacidad_nacional_id !== undefined,
                            )}
                            className={inputClasses}
                            {...register(`lotes.${index}.capacidad_nacional_id`, {
                              onChange: (event) => {
                                const capacidad = catalogo.data?.find(
                                  (item) => item.id === event.target.value,
                                );
                                setValue(
                                  `lotes.${index}.tipo_necesidad`,
                                  capacidad?.nombre ?? "",
                                  { shouldDirty: true },
                                );
                                setValue(
                                  `lotes.${index}.unidad`,
                                  capacidad?.unidad ?? "",
                                  { shouldDirty: true },
                                );
                              },
                            })}
                          >
                            <option value="">Elegí una capacidad</option>
                            {capacidadId && !capacidadSeleccionada && (
                              <option value={capacidadId} disabled>
                                {field.tipo_necesidad} (no disponible)
                              </option>
                            )}
                            {catalogo.data?.map((capacidad) => (
                              <option key={capacidad.id} value={capacidad.id}>
                                {capacidad.nombre}
                              </option>
                            ))}
                          </select>
                          {loteId !== null && !capacidadId && (
                            <p className="mt-2 text-sm text-slate-600">
                              Necesidad guardada: {field.tipo_necesidad}. Elegí una
                              capacidad del catálogo para actualizar este lote.
                            </p>
                          )}
                          {erroresLote?.capacidad_nacional_id && (
                            <p
                              id={`${prefijo}-capacidad-error`}
                              className="mt-2 text-sm text-red-700"
                            >
                              {erroresLote.capacidad_nacional_id.message}
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
                            readOnly
                            value={
                              capacidadSeleccionada?.unidad ??
                              valores[index]?.unidad ?? ""
                            }
                            aria-invalid={erroresLote?.unidad !== undefined}
                            aria-describedby={describedBy(
                              "unidad",
                              erroresLote?.unidad !== undefined,
                            )}
                            className={inputClasses}
                            placeholder="Se determina al elegir una capacidad"
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
                            htmlFor={`${prefijo}-riesgo`}
                            className="block text-sm font-semibold text-slate-800"
                          >
                            Riesgo requerido
                          </label>
                          <select
                            id={`${prefijo}-riesgo`}
                            className={inputClasses}
                            {...register(`lotes.${index}.riesgo_requerido`)}
                          >
                            <option value="">Usar gravedad de la emergencia</option>
                            {gravedades.map((gravedad) => (
                              <option key={gravedad} value={gravedad}>
                                {gravedadLabels[gravedad]}
                              </option>
                            ))}
                          </select>
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

                      {loteId === null ? (
                        fields.length > 1 && (
                          <button
                            type="button"
                            onClick={() => remove(index)}
                            className="action-button action-danger action-icon mt-5"
                            title={`Quitar lote ${index + 1}`}
                          >
                            <ActionIcon name="trash" />
                            <span className="sr-only">Quitar lote {index + 1}</span>
                          </button>
                        )
                      ) : confirmando === loteId ? (
                        <div
                          role="group"
                          aria-labelledby={`${prefijo}-confirmar`}
                          className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-900"
                        >
                          <p id={`${prefijo}-confirmar`} className="font-semibold">
                            ¿Eliminar el lote {index + 1}? Esta acción no se puede
                            deshacer.
                          </p>
                          {eliminacionError &&
                            eliminacion.variables?.loteId === loteId && (
                              <p role="alert" className="mt-1 text-red-800">
                                {eliminacionError}
                              </p>
                            )}
                          <div className="mt-3 flex flex-wrap gap-3">
                            <button
                              type="button"
                              disabled={ocupado}
                              onClick={() => eliminarGuardado(loteId)}
                              className="action-button action-danger"
                            >
                              {eliminacion.isPending
                                ? "Eliminando…"
                                : `Sí, eliminar lote ${index + 1}`}
                            </button>
                            <button
                              type="button"
                              disabled={eliminacion.isPending}
                              onClick={() => {
                                eliminacion.reset();
                                setConfirmando(null);
                              }}
                              className="action-button action-primary action-icon"
                              title="Cancelar"
                            >
                              <ActionIcon name="close" />
                              <span className="sr-only">Cancelar</span>
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          type="button"
                          disabled={ocupado}
                          onClick={() => {
                            eliminacion.reset();
                            setConfirmando(loteId);
                          }}
                          className="action-button action-danger action-icon mt-5"
                          title={`Eliminar lote ${index + 1}`}
                        >
                          <ActionIcon name="trash" />
                          <span className="sr-only">Eliminar lote {index + 1}</span>
                        </button>
                      )}
                    </fieldset>
                  </li>
                );
              })}
            </ol>
          </ScrollListado>

          {errors.lotes?.root && (
            <p role="alert" className="text-sm text-red-700">
              {errors.lotes.root.message}
            </p>
          )}

          <button
            type="button"
            disabled={bloqueado}
            onClick={() => append(loteVacio)}
            className="action-button action-primary"
            title="Agregar lote"
          >
            Agregar lote
          </button>

          {eliminacion.isSuccess && (
            <p
              role="status"
              className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm leading-6 font-semibold text-green-900"
            >
              Lote eliminado definitivamente.
            </p>
          )}

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
            disabled={bloqueado || sinCambios || !catalogoDisponible}
            className="action-button action-primary w-full"
            aria-busy={mutation.isPending}
          >
            {mutation.isPending
              ? "Guardando…"
              : sinCambios
                ? "Sin cambios para guardar"
                : "Guardar borrador"}
          </button>

          <div className="border-t border-slate-200 pt-6">
            <h3 className="text-base font-semibold text-slate-950">
              Publicación
            </h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              Publicar abre la convocatoria con todos los lotes guardados y ya
              no permite editarlos. Guardá primero cualquier cambio pendiente.
            </p>

            {publicacion.isSuccess && (
              <div
                role="status"
                className="mt-4 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm leading-6 text-green-900"
              >
                <p className="font-semibold">Convocatoria publicada.</p>
                <p className="mt-1">
                  Se incluyeron {publicacion.data.lotes.length} lote
                  {publicacion.data.lotes.length === 1 ? "" : "s"}.
                </p>
                {publicacion.data.bonita_generar_lotes_estado !== "COMPLETADA" && (
                  <p className="mt-1 text-amber-900">
                    La publicación local quedó confirmada, pero Bonita requiere
                    un reintento.
                    {publicacion.data.bonita_generar_lotes_ultimo_error
                      ? ` ${publicacion.data.bonita_generar_lotes_ultimo_error}`
                      : ""}
                  </p>
                )}
              </div>
            )}

            {publicacionError && (
              <p
                role="alert"
                className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm leading-6 text-red-800"
              >
                {publicacionError}
              </p>
            )}

            <button
              type="button"
              disabled={
                ocupado ||
                !puedePublicar ||
                convocatoriaPublicada ||
                publicacion.isSuccess
              }
              onClick={() => publicacion.mutate(csrfToken)}
              className="action-button action-warning mt-4 w-full"
              aria-busy={publicacion.isPending}
            >
              {publicacion.isPending
                ? "Publicando…"
                : convocatoriaPublicada || publicacion.isSuccess
                  ? "Convocatoria publicada"
                  : "Publicar convocatoria"}
            </button>
          </div>
        </form>
      )}
    </article>
  );
}
