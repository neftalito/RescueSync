import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactElement } from "react";
import { useForm, type UseFormRegisterReturn } from "react-hook-form";
import { useNavigate } from "react-router";

import { changePassword, logout } from "../api/auth";
import { ApiError } from "../api/client";
import { sessionQueryKey } from "../hooks/useSession";
import {
  changePasswordSchema,
  type ChangePasswordForm,
  type Session,
} from "../schemas/auth";

interface ChangePasswordPageProps {
  session: Session;
}

export function ChangePasswordPage({
  session,
}: ChangePasswordPageProps): ReactElement {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showPasswords, setShowPasswords] = useState(false);
  const {
    register,
    handleSubmit,
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
      navigate("/", { replace: true });
    },
  });
  const logoutMutation = useMutation({
    mutationFn: () => logout(session.csrf_token),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: sessionQueryKey });
      navigate("/login", { replace: true });
    },
  });
  const requestError =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.isError
        ? "No pudimos cambiar la contraseña. Intentá nuevamente."
        : null;
  const logoutError =
    logoutMutation.error instanceof ApiError
      ? logoutMutation.error.message
      : logoutMutation.isError
        ? "No pudimos cerrar la sesión. Intentá nuevamente."
        : null;

  return (
    <main className="grid min-h-screen place-items-center bg-slate-100 px-5 py-10">
      <section className="w-full max-w-lg rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-9">
        <p className="text-sm font-bold tracking-[0.16em] text-cyan-700 uppercase">
          Seguridad de la cuenta
        </p>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-950">
          {session.usuario.requiere_cambio_password
            ? "Creá una contraseña nueva"
            : "Cambiar contraseña"}
        </h1>
        <p className="mt-3 leading-7 text-slate-600">
          {session.usuario.requiere_cambio_password
            ? "La clave asignada es temporal. Debés reemplazarla antes de continuar."
            : "Al guardar, se cerrarán las demás sesiones abiertas de tu cuenta."}
        </p>

        <form
          className="mt-8 space-y-5"
          onSubmit={(event) => void handleSubmit((values) => mutation.mutate(values))(event)}
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

          {(requestError ?? logoutError) && (
            <p
              role="alert"
              className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
            >
              {requestError ?? logoutError}
            </p>
          )}

          <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
            {!session.usuario.requiere_cambio_password && (
              <button
                type="button"
                onClick={() => navigate("/")}
                className="rounded-xl border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700"
              >
                Cancelar
              </button>
            )}
            {session.usuario.requiere_cambio_password && (
              <button
                type="button"
                disabled={logoutMutation.isPending}
                onClick={() => logoutMutation.mutate()}
                className="rounded-xl border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 disabled:opacity-60"
              >
                {logoutMutation.isPending ? "Saliendo…" : "Cerrar sesión"}
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
    </main>
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
      <label htmlFor={id} className="block text-sm font-semibold text-slate-800">
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
