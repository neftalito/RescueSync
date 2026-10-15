import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactElement } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";

import { login } from "../api/auth";
import { ApiError } from "../api/client";
import { sessionQueryKey } from "../hooks/useSession";
import {
  loginSchema,
  type LoginCredentials,
  type Session,
} from "../schemas/auth";

export function LoginPage(): ReactElement {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showPassword, setShowPassword] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginCredentials>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  const mutation = useMutation({
    mutationFn: login,
    onSuccess: (session: Session) => {
      // Limpia todo el caché previo antes de fijar la nueva sesión: la
      // sesión anterior puede haber terminado por expiración (401 en
      // /auth/me) en vez de un logout explícito, y en ese caso nadie más
      // limpió el caché. Sin esto, esta pestaña podría mostrarle a esta
      // persona datos (por ejemplo la bandeja de emergencias) que
      // pertenecían a quien haya usado la sesión anterior.
      queryClient.clear();
      queryClient.setQueryData(sessionQueryKey, session);
      navigate(
        session.usuario.requiere_cambio_password ? "/opciones" : "/",
        { replace: true },
      );
    },
  });

  const submit = (credentials: LoginCredentials): void => {
    mutation.mutate(credentials);
  };
  const requestError =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.isError
        ? "No pudimos conectarnos con RescueSync. Intentá nuevamente."
        : null;

  return (
    <main className="min-h-screen bg-slate-950 text-slate-950 lg:grid lg:grid-cols-[minmax(0,1.05fr)_minmax(430px,0.95fr)]">
      <section className="relative hidden overflow-hidden px-12 py-14 text-white lg:flex lg:flex-col lg:justify-between">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_20%_10%,rgba(34,211,238,0.22),transparent_32%),radial-gradient(circle_at_80%_75%,rgba(14,165,233,0.15),transparent_30%)]" />
        <div className="relative">
          <Brand light />
        </div>
        <div className="relative max-w-xl pb-8">
          <p className="text-sm font-bold tracking-[0.18em] text-cyan-300 uppercase">
            Respuesta coordinada
          </p>
          <h1 className="mt-5 text-5xl font-bold leading-tight tracking-tight">
            Cada recurso cuenta cuando el tiempo apremia.
          </h1>
          <p className="mt-6 max-w-lg text-lg leading-8 text-slate-300">
            Municipios, centros regionales y organizaciones trabajando sobre una
            misma situación operativa.
          </p>
        </div>
        <p className="relative text-sm text-slate-400">
          Plataforma regional de coordinación ante emergencias
        </p>
      </section>

      <section className="flex min-h-screen items-center bg-slate-50 px-5 py-10 sm:px-10 lg:px-14">
        <div className="mx-auto w-full max-w-md">
          <div className="mb-10 lg:hidden">
            <Brand />
          </div>
          <p className="text-sm font-bold tracking-[0.16em] text-cyan-700 uppercase">
            Acceso seguro
          </p>
          <h2 className="mt-3 text-3xl font-bold tracking-tight text-slate-950 sm:text-4xl">
            Iniciá sesión
          </h2>
          <p className="mt-3 leading-7 text-slate-600">
            Usá las credenciales asignadas por tu organización.
          </p>

          <form
            className="mt-9 space-y-6"
            onSubmit={(event) => void handleSubmit(submit)(event)}
            noValidate
          >
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-semibold text-slate-800"
              >
                Correo electrónico
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                autoFocus
                aria-invalid={errors.email !== undefined}
                aria-describedby={errors.email ? "email-error" : undefined}
                className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3.5 text-base shadow-sm outline-none transition placeholder:text-slate-400 focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100"
                placeholder="nombre@organizacion.org"
                {...register("email")}
              />
              {errors.email && (
                <p id="email-error" className="mt-2 text-sm text-red-700">
                  {errors.email.message}
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-semibold text-slate-800"
              >
                Contraseña
              </label>
              <div className="relative mt-2">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  aria-invalid={errors.password !== undefined}
                  aria-describedby={
                    errors.password ? "password-error" : undefined
                  }
                  className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3.5 pr-24 text-base shadow-sm outline-none transition focus:border-cyan-600 focus:ring-4 focus:ring-cyan-100"
                  {...register("password")}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((visible) => !visible)}
                  className="absolute inset-y-0 right-3 my-auto h-fit rounded-lg px-2 py-1 text-sm font-semibold text-cyan-800 hover:bg-cyan-50 focus-visible:outline-2 focus-visible:outline-cyan-700"
                  aria-label={
                    showPassword ? "Ocultar contraseña" : "Mostrar contraseña"
                  }
                >
                  {showPassword ? "Ocultar" : "Mostrar"}
                </button>
              </div>
              {errors.password && (
                <p id="password-error" className="mt-2 text-sm text-red-700">
                  {errors.password.message}
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
              {mutation.isPending ? "Ingresando…" : "Ingresar a RescueSync"}
            </button>
          </form>

          <p className="mt-8 text-center text-sm leading-6 text-slate-500">
            Si no podés ingresar, contactá al responsable de tu organización.
          </p>
        </div>
      </section>
    </main>
  );
}

function Brand({ light = false }: { light?: boolean }): ReactElement {
  return (
    <div className="flex items-center gap-3" aria-label="RescueSync">
      <span className="grid size-11 place-items-center rounded-xl bg-cyan-600 text-lg font-black text-white shadow-lg shadow-cyan-950/20">
        R
      </span>
      <div>
        <p
          className={`text-lg font-black tracking-tight ${light ? "text-white" : "text-slate-950"}`}
        >
          RescueSync
        </p>
        <p className={`text-xs ${light ? "text-slate-400" : "text-slate-500"}`}>
          Coordinación regional
        </p>
      </div>
    </div>
  );
}
