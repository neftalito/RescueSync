import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactElement } from "react";
import { useForm, useWatch, type UseFormRegisterReturn } from "react-hook-form";
import { useNavigate } from "react-router";

import { ActionIcon } from "./ActionIcon";
import { changePassword } from "../api/auth";
import { ApiError } from "../api/client";
import { sessionQueryKey } from "../hooks/useSession";
import {
  changePasswordSchema,
  type ChangePasswordForm,
  type Session,
} from "../schemas/auth";

const hiddenPasswords = { actual: false, nueva: false, confirmacion: false };

interface ChangePasswordSectionProps {
  session: Session;
}

export function ChangePasswordSection({
  session,
}: ChangePasswordSectionProps): ReactElement {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showPasswords, setShowPasswords] = useState(hiddenPasswords);
  const {
    control,
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
  const passwords = useWatch({ control });
  const mutation = useMutation({
    mutationFn: (values: ChangePasswordForm) =>
      changePassword(values, session.csrf_token),
    onSuccess: (updatedSession: Session) => {
      queryClient.setQueryData(sessionQueryKey, updatedSession);
      reset();
      setShowPasswords(hiddenPasswords);
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
          placeholder="Ingresá tu contraseña actual"
          visible={showPasswords.actual}
          hasValue={Boolean(passwords.password_actual)}
          onToggle={() => setShowPasswords((previous) => ({
            ...previous,
            actual: !previous.actual,
          }))}
          error={errors.password_actual?.message}
          registration={register("password_actual")}
          autoComplete="current-password"
        />
        <PasswordField
          id="password-nueva"
          label="Contraseña nueva"
          placeholder="Usá entre 8 y 128 caracteres"
          visible={showPasswords.nueva}
          hasValue={Boolean(passwords.password_nueva)}
          onToggle={() => setShowPasswords((previous) => ({
            ...previous,
            nueva: !previous.nueva,
          }))}
          error={errors.password_nueva?.message}
          registration={register("password_nueva")}
          autoComplete="new-password"
        />
        <PasswordField
          id="confirmacion"
          label="Repetir contraseña nueva"
          placeholder="Volvé a ingresar la contraseña nueva"
          visible={showPasswords.confirmacion}
          hasValue={Boolean(passwords.confirmacion)}
          onToggle={() => setShowPasswords((previous) => ({
            ...previous,
            confirmacion: !previous.confirmacion,
          }))}
          error={errors.confirmacion?.message}
          registration={register("confirmacion")}
          autoComplete="new-password"
        />

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
                setShowPasswords(hiddenPasswords);
                mutation.reset();
              }}
              className="action-button"
              title="Cancelar"
            >
              Cancelar
            </button>
          )}
          <button
            type="submit"
            disabled={mutation.isPending}
            className="action-button action-primary"
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
  placeholder: string;
  visible: boolean;
  hasValue: boolean;
  onToggle: () => void;
  error?: string;
  registration: UseFormRegisterReturn;
  autoComplete: string;
}

function PasswordField({
  id,
  label,
  placeholder,
  visible,
  hasValue,
  onToggle,
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
      <div className="relative mt-2">
        <input
          id={id}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          placeholder={placeholder}
          aria-invalid={error !== undefined}
          aria-describedby={error ? errorId : undefined}
          className="w-full rounded-xl border border-slate-300 px-4 py-3 pr-16 outline-none focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100 [&::-ms-reveal]:hidden"
          {...registration}
        />
        {hasValue && (
          <button
            type="button"
            onClick={onToggle}
            className="action-button action-icon action-borderless password-visibility absolute inset-y-0 right-2 my-auto"
            aria-label={`${visible ? "Ocultar" : "Mostrar"}: ${label}`}
            title={`${visible ? "Ocultar" : "Mostrar"}: ${label}`}
            aria-controls={id}
            aria-pressed={visible}
          >
            <ActionIcon name={visible ? "eye-off" : "eye"} />
          </button>
        )}
      </div>
      {error && (
        <p id={errorId} className="mt-2 text-sm text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
