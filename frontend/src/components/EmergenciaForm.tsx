import { zodResolver } from "@hookform/resolvers/zod";
import { type ReactElement } from "react";
import { useForm } from "react-hook-form";

import { ApiError } from "../api/client";
import { useRegistrarEmergencia } from "../hooks/useRegistrarEmergencia";
import {
  emergenciaFormSchema,
  gravedadLabels,
  gravedades,
  type EmergenciaFormData,
} from "../schemas/emergencia";

interface EmergenciaFormProps {
  csrfToken: string;
}

const inputClasses =
  "mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3.5 text-base shadow-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100";

export function EmergenciaForm({ csrfToken }: EmergenciaFormProps): ReactElement {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<EmergenciaFormData>({
    resolver: zodResolver(emergenciaFormSchema),
    defaultValues: { gravedad: "MEDIA", zona: "", descripcion: "" },
  });
  const mutation = useRegistrarEmergencia();

  const submit = (datos: EmergenciaFormData): void => {
    mutation.mutate({ ...datos, csrfToken });
  };
  const requestError =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.isError
        ? "No pudimos registrar la emergencia. Intentá nuevamente."
        : null;
  const registrada = mutation.isSuccess ? mutation.data : null;

  const registrarOtra = (): void => {
    mutation.reset();
    reset({ gravedad: "MEDIA", zona: "", descripcion: "" });
  };

  return (
    <article className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <p className="text-sm font-semibold text-cyan-800">Municipio</p>
      <h3 className="mt-2 text-xl font-semibold text-slate-950">
        Registrar emergencia
      </h3>
      <p className="mt-2 leading-7 text-slate-600">
        Gravedad, zona afectada y descripción inicial. Queda en estado
        registrada hasta que el centro coordinador la tome.
      </p>

      {registrada ? (
        <div
          role="status"
          className="mt-6 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm leading-6 text-green-900"
        >
          <p className="font-semibold">
            Emergencia {registrada.id} registrada en estado {registrada.estado}.
          </p>
          <p className="mt-1">
            {gravedadLabels[registrada.gravedad]} · {registrada.zona}
          </p>
          <button
            type="button"
            onClick={registrarOtra}
            className="mt-4 w-full rounded-xl border border-green-700 bg-white px-4 py-2.5 text-sm font-semibold text-green-900 transition hover:bg-green-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green-700 sm:w-auto"
          >
            Registrar otra emergencia
          </button>
        </div>
      ) : (
        <form
          className="mt-6 space-y-6"
          onSubmit={(event) => void handleSubmit(submit)(event)}
          noValidate
        >
          <div>
            <label
              htmlFor="gravedad"
              className="block text-sm font-semibold text-slate-800"
            >
              Gravedad
            </label>
            <select
              id="gravedad"
              aria-invalid={errors.gravedad !== undefined}
              aria-describedby={errors.gravedad ? "gravedad-error" : undefined}
              className={inputClasses}
              {...register("gravedad")}
            >
              {gravedades.map((gravedad) => (
                <option key={gravedad} value={gravedad}>
                  {gravedadLabels[gravedad]}
                </option>
              ))}
            </select>
            {errors.gravedad && (
              <p id="gravedad-error" className="mt-2 text-sm text-red-700">
                {errors.gravedad.message}
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="zona"
              className="block text-sm font-semibold text-slate-800"
            >
              Zona afectada
            </label>
            <input
              id="zona"
              type="text"
              autoComplete="off"
              aria-invalid={errors.zona !== undefined}
              aria-describedby={errors.zona ? "zona-error" : undefined}
              className={inputClasses}
              placeholder="Barrio, localidad o referencia"
              {...register("zona")}
            />
            {errors.zona && (
              <p id="zona-error" className="mt-2 text-sm text-red-700">
                {errors.zona.message}
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="descripcion"
              className="block text-sm font-semibold text-slate-800"
            >
              Descripción inicial
            </label>
            <textarea
              id="descripcion"
              rows={4}
              aria-invalid={errors.descripcion !== undefined}
              aria-describedby={
                errors.descripcion ? "descripcion-error" : undefined
              }
              className={`${inputClasses} min-h-28 resize-y`}
              placeholder="Qué ocurrió, población afectada y accesos"
              {...register("descripcion")}
            />
            {errors.descripcion && (
              <p id="descripcion-error" className="mt-2 text-sm text-red-700">
                {errors.descripcion.message}
              </p>
            )}
          </div>

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
            {mutation.isPending ? "Registrando…" : "Registrar emergencia"}
          </button>
        </form>
      )}
    </article>
  );
}
