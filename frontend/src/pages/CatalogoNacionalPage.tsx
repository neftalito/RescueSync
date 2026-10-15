import { ListadoLocal } from "../components/ListadoProgresivo";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link } from "react-router";

import {
  catalogoAdminQueryKey,
  consultarCatalogoNacional,
  consultarUnidades,
  crearCapacidad,
  unidadesQueryKey,
} from "../api/catalogo";
import { ActionIcon } from "../components/ActionIcon";
import { ApiError } from "../api/client";
import type { Session } from "../schemas/auth";
import {
  capacidadCreateSchema,
  tipoCapacidadLabels,
  type CapacidadCreate,
} from "../schemas/catalogo";
import { capacidadSchema } from "../schemas/inventario";

function mensajeError(error: Error | null): string {
  return error instanceof ApiError
    ? error.message
    : "No pudimos completar la solicitud. Intentá nuevamente.";
}

export function CatalogoNacionalPage({
  session,
}: {
  session: Session;
}): ReactElement {
  const queryClient = useQueryClient();
  const catalogo = useQuery({
    queryKey: catalogoAdminQueryKey,
    queryFn: consultarCatalogoNacional,
    retry: false,
  });
  const unidades = useQuery({
    queryKey: unidadesQueryKey,
    queryFn: consultarUnidades,
    retry: false,
  });
  const {
    register,
    control,
    handleSubmit,
    reset,
    setValue,
    setError,
    formState: { errors },
  } = useForm<CapacidadCreate>({
    resolver: zodResolver(capacidadCreateSchema),
    defaultValues: {
      codigo: "",
      nombre: "",
      tipo: "SUMINISTRO",
      unidad: "",
      admiteFracciones: false,
    },
  });
  const tipo = useWatch({ control, name: "tipo" });
  const requiereEnteros = tipo === "PERSONAL" || tipo === "VEHICULO";
  const mutation = useMutation({
    mutationFn: (datos: CapacidadCreate) =>
      crearCapacidad(datos, session.csrf_token),
    onSuccess: async () => {
      reset();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: catalogoAdminQueryKey }),
        queryClient.invalidateQueries({
          queryKey: ["capacidades-coordinacion"],
        }),
        queryClient.invalidateQueries({ queryKey: ["inventario"] }),
      ]);
    },
  });
  const unidadesDisponibles = unidades.isSuccess && unidades.data.length > 0;

  const submit = (datos: CapacidadCreate): void => {
    if (!unidades.data?.some((unidad) => unidad.codigo === datos.unidad)) {
      setError("unidad", {
        message: "Elegí una unidad del catálogo disponible.",
      });
      return;
    }
    mutation.mutate(datos);
  };

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div>
            <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
              RescueSync
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-950">
              Catálogo nacional de capacidades
            </h1>
          </div>
          <Link
            to="/"
            className="action-button action-icon"
            title="Volver al inicio"
          >
            <ActionIcon name="home" />
            <span className="sr-only">Volver al inicio</span>
          </Link>
        </div>
      </header>

      <div className="mx-auto max-w-6xl space-y-8 px-5 py-8 sm:px-6">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <h2 className="text-xl font-bold text-slate-950">Crear capacidad</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Agregá una capacidad para que los coordinadores puedan seleccionarla
            en sus lotes y las ONG puedan registrar recursos. Las unidades
            disponibles están predefinidas.
          </p>
          {unidades.isPending && (
            <p role="status" className="mt-4">
              Cargando unidades…
            </p>
          )}
          {unidades.isError && (
            <div
              role="alert"
              className="mt-4 rounded-xl bg-red-50 p-4 text-red-800"
            >
              <p>{mensajeError(unidades.error)}</p>
              <button
                type="button"
                disabled={unidades.isFetching}
                onClick={() => void unidades.refetch()}
                className="action-button action-icon mt-2"
                title="Reintentar unidades"
              >
                <ActionIcon name="refresh" />
                <span className="sr-only">Reintentar unidades</span>
              </button>
            </div>
          )}
          {unidades.isSuccess && unidades.data.length === 0 && (
            <p role="status" className="mt-4 text-amber-800">
              No hay unidades disponibles. La administración del sistema debe
              cargar el catálogo predefinido.
            </p>
          )}

          <form
            className="mt-5"
            onSubmit={(event) => void handleSubmit(submit)(event)}
            noValidate
            aria-busy={mutation.isPending}
          >
            <fieldset
              disabled={mutation.isPending || !unidadesDisponibles}
              className="grid min-w-0 gap-5 sm:grid-cols-2 disabled:opacity-70"
            >
              <legend className="sr-only">Datos de la nueva capacidad</legend>
              <div>
                <label
                  htmlFor="capacidad-codigo"
                  className="block text-sm font-semibold text-slate-800"
                >
                  Código
                </label>
                <input
                  id="capacidad-codigo"
                  className="form-input mt-2"
                  placeholder="ALIMENTOS"
                  autoComplete="off"
                  aria-invalid={!!errors.codigo}
                  aria-describedby={
                    errors.codigo ? "codigo-error" : "codigo-ayuda"
                  }
                  {...register("codigo")}
                />
                <p id="codigo-ayuda" className="mt-2 text-sm text-slate-500">
                  Identificador único con letras, números y guion bajo.
                </p>
                {errors.codigo && (
                  <p id="codigo-error" className="mt-2 text-sm text-red-700">
                    {errors.codigo.message}
                  </p>
                )}
              </div>
              <div>
                <label
                  htmlFor="capacidad-nombre"
                  className="block text-sm font-semibold text-slate-800"
                >
                  Nombre de la capacidad
                </label>
                <input
                  id="capacidad-nombre"
                  className="form-input mt-2"
                  placeholder="Alimentos no perecederos"
                  autoComplete="off"
                  aria-invalid={!!errors.nombre}
                  aria-describedby={errors.nombre ? "nombre-error" : undefined}
                  {...register("nombre")}
                />
                {errors.nombre && (
                  <p id="nombre-error" className="mt-2 text-sm text-red-700">
                    {errors.nombre.message}
                  </p>
                )}
              </div>
              <div>
                <label
                  htmlFor="capacidad-tipo"
                  className="block text-sm font-semibold text-slate-800"
                >
                  Tipo de recurso
                </label>
                <select
                  id="capacidad-tipo"
                  className="form-input mt-2"
                  {...register("tipo", {
                    onChange: (event) => {
                      if (["PERSONAL", "VEHICULO"].includes(event.target.value))
                        setValue("admiteFracciones", false, {
                          shouldDirty: true,
                          shouldValidate: true,
                        });
                    },
                  })}
                >
                  {capacidadSchema.shape.tipo.options.map((valor) => (
                    <option key={valor} value={valor}>
                      {tipoCapacidadLabels[valor]}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  htmlFor="capacidad-unidad"
                  className="block text-sm font-semibold text-slate-800"
                >
                  Unidad
                </label>
                <select
                  id="capacidad-unidad"
                  className="form-input mt-2"
                  aria-invalid={!!errors.unidad}
                  aria-describedby={errors.unidad ? "unidad-error" : undefined}
                  {...register("unidad")}
                >
                  <option value="">Elegí una unidad</option>
                  {unidades.data?.map((unidad) => (
                    <option key={unidad.codigo} value={unidad.codigo}>
                      {unidad.nombre}
                    </option>
                  ))}
                </select>
                {errors.unidad && (
                  <p id="unidad-error" className="mt-2 text-sm text-red-700">
                    {errors.unidad.message}
                  </p>
                )}
              </div>
              <div className="sm:col-span-2">
                <label className="flex items-center gap-3 text-sm font-semibold text-slate-800">
                  <input
                    type="checkbox"
                    disabled={requiereEnteros}
                    aria-describedby="fracciones-ayuda"
                    {...register("admiteFracciones")}
                  />
                  Permitir cantidades fraccionadas
                </label>
                <p
                  id="fracciones-ayuda"
                  className="mt-2 text-sm text-slate-500"
                >
                  {requiereEnteros
                    ? "Personal y vehículos requieren cantidades enteras."
                    : "Habilitá esta opción para cantidades como 1,5 kg o 2,5 litros."}
                </p>
              </div>
              <button
                type="submit"
                className="action-button action-primary sm:col-span-2"
              >
                {mutation.isPending ? "Creando…" : "Crear capacidad"}
              </button>
            </fieldset>
          </form>
          {mutation.isError && (
            <p
              role="alert"
              className="mt-4 rounded-xl bg-red-50 p-4 text-sm text-red-800"
            >
              {mensajeError(mutation.error)}
            </p>
          )}
          {mutation.isSuccess && (
            <p
              role="status"
              className="mt-4 rounded-xl bg-green-50 p-4 text-sm text-green-900"
            >
              Capacidad «{mutation.data.nombre}» creada.
            </p>
          )}
        </section>

        <section
          aria-labelledby="capacidades-registradas"
          className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6"
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2
              id="capacidades-registradas"
              className="text-xl font-bold text-slate-950"
            >
              Capacidades disponibles
            </h2>
            <button
              type="button"
              disabled={catalogo.isFetching}
              onClick={() => void catalogo.refetch()}
              className="action-button action-icon"
              title="Actualizar catálogo"
            >
              <ActionIcon name="refresh" />
              <span className="sr-only">Actualizar catálogo</span>
            </button>
          </div>
          {catalogo.isPending && (
            <p role="status" className="mt-4">
              Cargando capacidades…
            </p>
          )}
          {catalogo.isError && (
            <p role="alert" className="mt-4 text-red-700">
              {mensajeError(catalogo.error)}
            </p>
          )}
          {catalogo.isSuccess && catalogo.data.length === 0 && (
            <p className="mt-4 text-slate-600">
              Todavía no hay capacidades activas.
            </p>
          )}
          {catalogo.data && (
            <ListadoLocal items={catalogo.data} etiqueta="Capacidades disponibles" className="mt-4">
              {(visibles) => (
                <ul className="mt-5 grid gap-4 sm:grid-cols-2">
                  {visibles.map((capacidad) => (
                    <li
                      key={capacidad.id}
                      className="min-w-0 rounded-xl border border-slate-200 p-4"
                    >
                      <h3 className="font-semibold break-words text-slate-950">
                        {capacidad.nombre}
                      </h3>
                      <p className="mt-1 text-sm break-words text-slate-500">
                        {capacidad.codigo}
                      </p>
                      <p className="mt-2 text-sm text-slate-700">
                        {tipoCapacidadLabels[capacidad.tipo]} · {capacidad.unidad}
                      </p>
                      <p className="mt-1 text-sm text-slate-500">
                        {capacidad.admiteFracciones
                          ? "Admite fracciones"
                          : "Cantidades enteras"}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </ListadoLocal>
          )}
        </section>
      </div>
    </main>
  );
}
