import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactElement } from "react";
import { useForm, type UseFormRegisterReturn } from "react-hook-form";
import { useNavigate } from "react-router";

import { changePassword } from "../api/auth";
import { ApiError } from "../api/client";
import { sessionQueryKey } from "../hooks/useSession";
import {
  changePasswordSchema,
  type ChangePasswordForm,
  type Session,
} from "../schemas/auth";

interface ChangePasswordSectionProps {
  session: Session;
}

export function ChangePasswordSection({
  session,
}: ChangePasswordSectionProps): ReactElement {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showPasswords, setShowPasswords] = useState(false);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ChangePasswordForm>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: {
      password_actual: "",
      password_nueva: "",
      confirmacion: "",
    },
  });
  const mutation = useMutation({
    mutationFn: (values: ChangePasswordForm) =>
      changePassword(values, session.csrf_token),
    onSuccess: (updatedSession: Session) => {
      queryClient.setQueryData(sessionQueryKey, updatedSession);
      reset();
      setShowPasswords(false);
      if (session.usuario.requiere_cambio_password) {
        navigate("/", { replace: true });
      }
    },
  });
  const requestError =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.isError
        ? "No pudimos cambiar la contraseña. Intentá nuevamente."
        : null;
  return (
    <section
      aria-labelledby="cambiar-password-titulo"
      className="w-full max-w-2xl rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-9"
    >
      <p className="text-sm font-bold tracking-[0.16em] text-cyan-700 uppercase">
        Seguridad de la cuenta
      </p>
      <h2
        id="cambiar-password-titulo"
        className="mt-3 text-2xl font-bold tracking-tight text-slate-950"
      >
        Cambiar contraseña
      </h2>
      <p className="mt-3 leading-7 text-slate-600">
        {session.usuario.requiere_cambio_password
          ? "La clave asignada es temporal. Debés reemplazarla antes de continuar."
          : "Al guardar, se cerrarán las demás sesiones abiertas de tu cuenta."}
      </p>

      <form
        className="mt-8 space-y-5"
        onSubmit={(event) =>
          void handleSubmit((values) => mutation.mutate(values))(event)
        }
        noValidate
      >
        <PasswordField
          id="password-actual"
          label="Contraseña actual"
          visible={showPasswords}
          error={errors.password_actual?.message}
          registration={register("password_actual")}
          autoComplete="current-password"
        />
        <PasswordField
          id="password-nueva"
          label="Contraseña nueva"
          visible={showPasswords}
          error={errors.password_nueva?.message}
          registration={register("password_nueva")}
          autoComplete="new-password"
        />
        <PasswordField
          id="confirmacion"
          label="Repetir contraseña nueva"
          visible={showPasswords}
          error={errors.confirmacion?.message}
          registration={register("confirmacion")}
          autoComplete="new-password"
        />

        <label className="flex items-center gap-3 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={showPasswords}
            onChange={(event) => setShowPasswords(event.target.checked)}
            className="size-4 rounded border-slate-300"
          />
          Mostrar contraseñas
        </label>

        {requestError && (
          <p
            role="alert"
            className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          >
            {requestError}
          </p>
        )}

        {mutation.isSuccess && (
          <p
            role="status"
            className="rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800"
          >
            Contraseña actualizada. Se cerraron las demás sesiones abiertas de
            tu cuenta.
          </p>
        )}

        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
          {!session.usuario.requiere_cambio_password && (
            <button
              type="button"
              onClick={() => {
                reset();
                setShowPasswords(false);
                mutation.reset();
              }}
              className="rounded-xl border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700"
            >
              Cancelar
            </button>
          )}
          <button
            type="submit"
            disabled={mutation.isPending}
            className="rounded-xl bg-cyan-700 px-5 py-3 text-sm font-bold text-white hover:bg-cyan-800 disabled:cursor-wait disabled:opacity-60"
          >
            {mutation.isPending ? "Guardando…" : "Guardar contraseña"}
          </button>
        </div>
      </form>
    </section>
  );
}

interface PasswordFieldProps {
  id: string;
  label: string;
  visible: boolean;
  error?: string;
  registration: UseFormRegisterReturn;
  autoComplete: string;
}

function PasswordField({
  id,
  label,
  visible,
  error,
  registration,
  autoComplete,
}: PasswordFieldProps): ReactElement {
  const errorId = `${id}-error`;
  return (
    <div>
      <label
        htmlFor={id}
        className="block text-sm font-semibold text-slate-800"
      >
        {label}
      </label>
      <input
        id={id}
        type={visible ? "text" : "password"}
        autoComplete={autoComplete}
        aria-invalid={error !== undefined}
        aria-describedby={error ? errorId : undefined}
        className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 outline-none focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100"
        {...registration}
      />
      {error && (
        <p id={errorId} className="mt-2 text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
