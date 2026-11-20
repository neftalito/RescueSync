import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { type ReactElement } from "react";
import { useForm } from "react-hook-form";

import { ApiError } from "../api/client";
import { consultarPrioridad } from "../api/emergencias";
import { useRegistrarEmergencia } from "../hooks/useRegistrarEmergencia";
import {
  emergenciaFormSchema,
  gravedadLabels,
  gravedades,
  zonasPrioridad,
  type EmergenciaFormData,
  type SolicitudPrioridad,
} from "../schemas/emergencia";

interface EmergenciaFormProps {
  csrfToken: string;
}

const inputClasses =
  "mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3.5 text-base shadow-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100";

export function EmergenciaForm({ csrfToken }: EmergenciaFormProps): ReactElement {
  const {
    register,
    getValues,
    handleSubmit,
    reset,
    trigger,
    formState: { errors },
  } = useForm<EmergenciaFormData>({
    resolver: zodResolver(emergenciaFormSchema),
    defaultValues: { gravedad: "MEDIA", zona: "", descripcion: "" },
  });
  const mutation = useRegistrarEmergencia();
  const consulta = useMutation({
    mutationFn: (datos: SolicitudPrioridad) => consultarPrioridad(datos, csrfToken),
  });

  const submit = (datos: EmergenciaFormData): void => {
    if (
      consulta.data &&
      consulta.variables.gravedad === datos.gravedad &&
      consulta.variables.zona === datos.zona
    ) {
      mutation.mutate(
        { ...datos, csrfToken, comprobante_prioridad: consulta.data.comprobante },
        {
          onError: (error) => {
            if (error instanceof ApiError && error.status === 409) consulta.reset();
          },
        },
      );
    }
  };
  const solicitarPrioridad = async (): Promise<void> => {
    if (await trigger(["gravedad", "zona"])) {
      mutation.reset();
      const { gravedad, zona } = getValues();
      consulta.mutate({ gravedad, zona });
    }
  };
  const reiniciarSolicitudes = (): void => {
    consulta.reset();
    mutation.reset();
  };
  const requestError =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.isError
        ? "No pudimos registrar la emergencia. Intentá nuevamente."
        : null;
  const errorConsulta =
    consulta.error instanceof ApiError
      ? consulta.error.message
      : "No pudimos consultar la prioridad. Intentá nuevamente.";
  const registrada = mutation.isSuccess ? mutation.data : null;

  const registrarOtra = (): void => {
    reiniciarSolicitudes();
    reset({ gravedad: "MEDIA", zona: "", descripcion: "" });
  };

  return (
    <article className="w-full max-w-2xl rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
      <p className="text-sm font-semibold text-cyan-800">Municipio</p>
      <h3 className="mt-2 text-xl font-semibold text-slate-950">
        Registrar emergencia
      </h3>
      <p className="mt-2 leading-7 text-slate-600">
        Consultá la prioridad según la gravedad y la zona afectada. Después podés
        registrar la emergencia para que la tome el centro coordinador.
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
          {registrada.prioridad !== null && (
            <p className="mt-1">Prioridad {registrada.prioridad} de 10</p>
          )}
          <button
            type="button"
            onClick={registrarOtra}
            className="action-button action-success mt-4 w-full sm:w-auto"
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
              disabled={mutation.isPending}
              {...register("gravedad", { onChange: reiniciarSolicitudes })}
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
            <select
              id="zona"
              aria-invalid={errors.zona !== undefined}
              aria-describedby={errors.zona ? "zona-error" : undefined}
              className={inputClasses}
              disabled={mutation.isPending}
              {...register("zona", { onChange: reiniciarSolicitudes })}
            >
              <option value="">Elegí una zona</option>
              {zonasPrioridad.map(({ codigo, etiqueta }) => (
                <option key={codigo} value={codigo}>
                  {etiqueta}
                </option>
              ))}
            </select>
            {errors.zona && (
              <p id="zona-error" className="mt-2 text-sm text-red-700">
                {errors.zona.message}
              </p>
            )}
          </div>

          <div className="space-y-3">
            <button
              type="button"
              onClick={() => void solicitarPrioridad()}
              disabled={consulta.isPending || mutation.isPending}
              className="action-button w-full"
            >
              {consulta.isPending ? "Consultando…" : "Consultar prioridad"}
            </button>
            {consulta.data && (
              <p role="status" className="font-semibold text-cyan-800">
                Prioridad {consulta.data.prioridad} de 10
              </p>
            )}
            {consulta.isError && (
              <p role="alert" className="text-sm text-red-700">
                {errorConsulta}
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
              placeholder="Qué ocurrió, barrio o localidad, población afectada y accesos"
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
            disabled={mutation.isPending || !consulta.data}
            className="action-button action-primary w-full"
          >
            {mutation.isPending ? "Registrando…" : "Registrar emergencia"}
          </button>
        </form>
      )}
    </article>
  );
}
