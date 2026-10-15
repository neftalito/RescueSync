import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactElement, useEffect, useRef, useState } from "react";
import { useFieldArray, useForm, useWatch } from "react-hook-form";
import { Link } from "react-router";

import { ApiError } from "../api/client";
import { consultarRecursos } from "../api/inventario";
import { sessionQueryKey } from "../hooks/useSession";
import type { Session } from "../schemas/auth";
import { RecursosOferta } from "./RecursosOferta";
import { useActualizarOferta } from "../hooks/useActualizarOferta";
import { useConvocatoriasAbiertas } from "../hooks/useConvocatoriasAbiertas";
import { useMisOfertas } from "../hooks/useMisOfertas";
import { useRegistrarOferta } from "../hooks/useRegistrarOferta";
import type { LotePublicado } from "../schemas/convocatoria";
import {
  ofertaFormSchema,
  tipoAporteLabels,
  tiposAporte,
  type OfertaFormData,
} from "../schemas/oferta";
import {
  formatearCantidad,
  formatearCantidadParaFormulario,
} from "../utils/cantidades";

interface OfertaFormProps {
  csrfToken: string;
  ofertaId?: number;
  loteInicialId?: number;
}

const inputClasses =
  "mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-base shadow-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100";

function nuevoItem(lote: LotePublicado): OfertaFormData["items"][number] {
  return {
    lote_id: lote.lote_id,
    tipo: "RECURSO",
    descripcion: lote.tipo_necesidad,
    cantidad_ofrecida: "",
    cantidad_publicada: lote.cantidad_publicada,
    unidad: lote.unidad_publicada,
    requiere_desglose: Boolean(lote.capacidad_nacional_id),
    aportes: [],
  };
}

export function OfertaForm({
  csrfToken,
  ofertaId,
  loteInicialId,
}: OfertaFormProps): ReactElement {
  const session = useQueryClient().getQueryData<Session>(sessionQueryKey);
  const convocatoriasQuery = useConvocatoriasAbiertas();
  const ofertasQuery = useMisOfertas();
  const registrarMutation = useRegistrarOferta();
  const actualizarMutation = useActualizarOferta();
  const [loteParaAgregar, setLoteParaAgregar] = useState("");
  const edicionInicializada = useRef(false);
  const loteInicializado = useRef(false);
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
  const { fields, append, remove } = useFieldArray({
    control,
    name: "items",
  });
  const convocatoriaId = useWatch({ control, name: "convocatoria_id" });
  const items = useWatch({ control, name: "items" }) ?? [];
  const editando = ofertaId !== undefined;
  const oferta = ofertasQuery.data?.find((item) => item.id === ofertaId);
  const convocatoriasAbiertas = convocatoriasQuery.data ?? [];
  const convocatoriaInicial = convocatoriasAbiertas.find((item) =>
    item.lotes.some((lote) => lote.lote_id === loteInicialId),
  );
  const ofertaInicial = ofertasQuery.data?.find(
    (item) => item.convocatoria_id === convocatoriaInicial?.id,
  );
  const convocatoriasConOferta = new Set(
    (ofertasQuery.data ?? []).map((item) => item.convocatoria_id),
  );
  const convocatorias = editando
    ? convocatoriasAbiertas.filter(
        (item) => oferta === undefined || item.id === oferta.convocatoria_id,
      )
    : convocatoriasAbiertas.filter(
        (item) => !convocatoriasConOferta.has(item.id),
      );
  const convocatoriaBuscadaId =
    editando && oferta !== undefined ? oferta.convocatoria_id : convocatoriaId;
  const convocatoria = convocatoriasAbiertas.find(
    (item) => item.id === convocatoriaBuscadaId,
  );
  const lotes = convocatoria?.lotes ?? [];
  const recursosQuery = useQuery({
    queryKey: ["recursos-oferta", session?.usuario.id, convocatoriaId], queryFn: consultarRecursos,
    enabled: items.some((i) => i.requiere_desglose), retry: false, gcTime: 0,
  });
  const lotesAgregados = new Set(items.map((item) => item.lote_id));
  const lotesSinAgregar = lotes.filter(
    (lote) => !lotesAgregados.has(lote.lote_id),
  );
  const mutationError = editando
    ? actualizarMutation.error
    : registrarMutation.error;
  const mutationIsError = editando
    ? actualizarMutation.isError
    : registrarMutation.isError;
  const mutationIsPending = editando
    ? actualizarMutation.isPending
    : registrarMutation.isPending;
  const mutationData = editando
    ? actualizarMutation.data
    : registrarMutation.data;
  const requestError =
    mutationError instanceof ApiError
      ? mutationError.message
      : mutationIsError
        ? `No pudimos ${editando ? "actualizar" : "presentar"} la oferta. Intentá nuevamente.`
        : null;
  const itemsError = errors.items?.root?.message ?? errors.items?.message;

  useEffect(() => {
    if (
      !editando ||
      edicionInicializada.current ||
      oferta === undefined ||
      convocatoria === undefined
    ) {
      return;
    }
    reset({
      convocatoria_id: oferta.convocatoria_id,
      observaciones: oferta.observaciones ?? "",
      items: oferta.items.map((item) => {
        const lote = convocatoria.lotes.find(
          (opcion) => opcion.lote_id === item.lote_id,
        );
        return {
          lote_id: item.lote_id,
          tipo: item.tipo,
          descripcion: item.descripcion,
          cantidad_ofrecida: formatearCantidadParaFormulario(
            item.cantidad_ofrecida,
          ),
          cantidad_publicada: lote?.cantidad_publicada ?? "0",
          unidad: item.unidad,
          requiere_desglose: Boolean(lote?.capacidad_nacional_id),
          aportes: (item.aportes ?? []).map((a) => ({ recurso_nacional_id: a.recurso_nacional_id, cantidad: a.cantidad })),
        };
      }),
    });
    edicionInicializada.current = true;
  }, [convocatoria, editando, oferta, reset]);

  useEffect(() => {
    if (
      editando ||
      loteInicializado.current ||
      !convocatoriasQuery.isSuccess ||
      !ofertasQuery.isSuccess ||
      convocatoriaInicial === undefined ||
      ofertaInicial !== undefined
    ) {
      return;
    }
    const lote = convocatoriaInicial.lotes.find(
      (item) => item.lote_id === loteInicialId,
    );
    if (lote === undefined) return;
    reset({
      convocatoria_id: convocatoriaInicial.id,
      observaciones: "",
      items: [nuevoItem(lote)],
    });
    loteInicializado.current = true;
  }, [
    convocatoriaInicial,
    convocatoriasQuery.isSuccess,
    editando,
    loteInicialId,
    ofertaInicial,
    ofertasQuery.isSuccess,
    reset,
  ]);

  const cambiarConvocatoria = (convocatoriaNuevaId: number): void => {
    reset({
      convocatoria_id: convocatoriaNuevaId,
      observaciones: "",
      items: [],
    });
    setLoteParaAgregar("");
    registrarMutation.reset();
  };

  const agregarLote = (): void => {
    const lote = lotes.find((opcion) => opcion.lote_id === Number(loteParaAgregar));
    if (lote === undefined || lotesAgregados.has(lote.lote_id)) return;
    append(nuevoItem(lote));
    setLoteParaAgregar("");
  };

  const presentar = (datos: OfertaFormData): void => {
    if (oferta === undefined) {
      registrarMutation.mutate({ datos, csrfToken });
      return;
    }
    actualizarMutation.mutate({
      ofertaId: oferta.id,
      datos,
      versionBloqueo: oferta.version_bloqueo,
      csrfToken,
    });
  };

  // La confirmación de una escritura ya completada tiene prioridad sobre la
  // recarga de consultas invalidada por la mutación. La convocatoria puede
  // vencer entre ambas respuestas sin que eso invalide la oferta creada.
  if (mutationData !== undefined) {
    return (
      <article className="w-full max-w-3xl rounded-2xl border border-green-200 bg-white p-6 shadow-sm sm:p-8">
        <div
          role="status"
          className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm leading-6 text-green-900"
        >
          <p className="font-semibold">
            Oferta {mutationData.id} {editando ? "actualizada" : "presentada"}{" "}
            correctamente.
          </p>
          <p className="mt-1">
            La versión {mutationData.version_actual} contiene{" "}
            {mutationData.items.length} lotes en estado {mutationData.estado}.
          </p>
        </div>
        <Link
          to="/mis-ofertas"
          className="mt-5 inline-flex rounded-xl bg-cyan-700 px-5 py-3 text-sm font-bold text-white hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700"
        >
          Ver mis ofertas
        </Link>
      </article>
    );
  }

  if (convocatoriasQuery.isPending || ofertasQuery.isPending) {
    return (
      <article className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <p role="status" className="text-sm text-slate-600">
          Cargando convocatorias disponibles…
        </p>
      </article>
    );
  }

  if (convocatoriasQuery.isError || ofertasQuery.isError) {
    return (
      <article className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <p role="alert" className="text-sm leading-6 text-red-800">
          {convocatoriasQuery.error instanceof ApiError
            ? convocatoriasQuery.error.message
            : ofertasQuery.error instanceof ApiError
              ? ofertasQuery.error.message
              : "No pudimos cargar las convocatorias. Intentá nuevamente."}
        </p>
        <button
          type="button"
          onClick={() => {
            void convocatoriasQuery.refetch();
            void ofertasQuery.refetch();
          }}
          className="mt-4 rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700"
        >
          Reintentar
        </button>
      </article>
    );
  }

  if (editando && oferta === undefined) {
    return (
      <article className="w-full max-w-3xl rounded-2xl border border-red-200 bg-white p-6 shadow-sm sm:p-8">
        <p role="alert" className="text-sm leading-6 text-red-800">
          La oferta no existe o no pertenece a tu ONG.
        </p>
      </article>
    );
  }

  if (
    editando &&
    (oferta === undefined || !oferta.editable || convocatoria === undefined)
  ) {
    return (
      <article className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <p role="status" className="text-sm leading-6 text-slate-600">
          La convocatoria cerró y esta oferta ya no puede modificarse.
        </p>
        <Link
          to="/mis-ofertas"
          className="mt-5 inline-flex rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
        >
          Volver a mis ofertas
        </Link>
      </article>
    );
  }

  if (!editando && loteInicialId !== undefined) {
    if (convocatoriaInicial === undefined) {
      return (
        <article className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <p role="status" className="text-sm leading-6 text-slate-600">
            El lote seleccionado ya no está disponible en una convocatoria abierta.
          </p>
          <Link
            to="/convocatorias"
            className="mt-5 inline-flex rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Volver a convocatorias
          </Link>
        </article>
      );
    }
    if (ofertaInicial !== undefined) {
      return (
        <article className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <p role="status" className="text-sm leading-6 text-slate-600">
            Tu ONG ya presentó una oferta para esta convocatoria. Podés modificarla
            para incluir este lote.
          </p>
          <Link
            to={`/ofertas/${ofertaInicial.id}/editar`}
            className="mt-5 inline-flex rounded-xl bg-cyan-700 px-5 py-3 text-sm font-bold text-white hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700"
          >
            Modificar oferta existente
          </Link>
        </article>
      );
    }
  }

  if (convocatorias.length === 0) {
    return (
      <article className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
        <p role="status" className="text-sm leading-6 text-slate-600">
          En este momento no hay convocatorias abiertas sin una oferta de tu ONG.
        </p>
      </article>
    );
  }

  return (
    <article className="w-full max-w-3xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <p className="text-sm font-semibold text-cyan-800">Representante de ONG</p>
      <h2 className="mt-2 text-2xl font-semibold text-slate-950">
        {editando ? "Modificar oferta" : "Presentar oferta"}
      </h2>
      <p className="mt-2 leading-7 text-slate-600">
        {editando
          ? "Actualizá los aportes. Conservaremos la versión anterior para mantener la trazabilidad."
          : "Elegí una convocatoria y ofrecé recursos, personal o ambos para uno o más lotes."}{" "}
        Cada cantidad puede cubrir una parte o el total publicado, pero no superarlo.
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
              onChange: (event) =>
                cambiarConvocatoria(Number(event.target.value)),
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
                      {formatearCantidad(lote.cantidad_publicada)}{" "}
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
                        Publicado: {formatearCantidad(lote.cantidad_publicada)}{" "}
                        {lote.unidad_publicada}
                      </p>
                    )}
                    {lote?.capacidad_nacional_id && <>
                      {recursosQuery.isPending && <p role="status">Cargando tu inventario…</p>}
                      {recursosQuery.isError && <p role="alert">{recursosQuery.error instanceof ApiError ? recursosQuery.error.message : "No pudimos consultar el inventario."} <Link to="/mis-recursos">Ir a Mis recursos</Link></p>}
                      <RecursosOferta index={index} control={control} register={register} errores={errors} recursos={(recursosQuery.isError ? [] : recursosQuery.data ?? []).filter((r) => r.activo && r.capacidadId === lote.capacidad_nacional_id && r.unidad === lote.unidad_publicada)} />
                    </>}
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
                    <input
                      type="hidden"
                      {...register(`items.${index}.cantidad_publicada`)}
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
          disabled={mutationIsPending}
          className="flex w-full items-center justify-center rounded-xl bg-cyan-700 px-5 py-3.5 text-base font-bold text-white shadow-sm transition hover:bg-cyan-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-700 disabled:cursor-wait disabled:opacity-70"
        >
          {mutationIsPending
            ? `${editando ? "Actualizando" : "Presentando"} oferta…`
            : editando
              ? "Guardar cambios"
              : "Presentar oferta"}
        </button>
      </form>
    </article>
  );
}
