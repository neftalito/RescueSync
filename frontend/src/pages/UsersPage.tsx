import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactElement } from "react";
import { useForm, useWatch } from "react-hook-form";
import { Link } from "react-router";

import { ApiError } from "../api/client";
import {
  createUser,
  deactivateUser,
  getOrganizations,
  getUsers,
  reactivateUser,
  resetUserPassword,
  updateUser,
} from "../api/users";
import { sessionQueryKey } from "../hooks/useSession";
import { roleLabels, roles, type Role, type Session } from "../schemas/auth";
import {
  createUserSchema,
  editUserSchema,
  resetPasswordSchema,
  type CreateUserForm,
  type EditUserForm,
  type ManagedUser,
  type Organization,
  type ResetPasswordForm,
} from "../schemas/users";

const usersQueryKey = ["users"] as const;
const organizationsQueryKey = ["organizations"] as const;
const organizationTypeByRole: Partial<Record<Role, Organization["tipo"]>> = {
  OPERADOR_MUNICIPAL: "MUNICIPIO",
  COORDINADOR_REGIONAL: "CENTRO_COORDINADOR",
  REPRESENTANTE_ONG: "ONG",
};

interface UsersPageProps {
  session: Session;
}

export function UsersPage({ session }: UsersPageProps): ReactElement {
  const queryClient = useQueryClient();
  const [editingUser, setEditingUser] = useState<ManagedUser | null>(null);
  const [resettingUser, setResettingUser] = useState<ManagedUser | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const users = useQuery({ queryKey: usersQueryKey, queryFn: getUsers });
  const organizations = useQuery({
    queryKey: organizationsQueryKey,
    queryFn: getOrganizations,
  });
  const statusMutation = useMutation({
    mutationFn: async ({ user, active }: { user: ManagedUser; active: boolean }) => {
      if (active) {
        return reactivateUser(user.id, session.csrf_token);
      }
      await deactivateUser(user.id, session.csrf_token);
      return null;
    },
    onSuccess: async (_, variables) => {
      setFeedback(
        variables.active ? "Usuario reactivado." : "Usuario desactivado.",
      );
      await queryClient.invalidateQueries({ queryKey: usersQueryKey });
    },
  });
  const loadError = users.error ?? organizations.error;
  const actionError = statusMutation.error;

  const changeStatus = (user: ManagedUser): void => {
    if (
      user.activo &&
      !window.confirm(
        `¿Desactivar a ${user.email}? Ya no podrá iniciar sesión.`,
      )
    ) {
      return;
    }
    setFeedback(null);
    statusMutation.mutate({ user, active: !user.activo });
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
              Administración de usuarios
            </h1>
          </div>
          <Link
            to="/"
            className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50"
          >
            Volver al inicio
          </Link>
        </div>
      </header>

      <div className="mx-auto max-w-6xl space-y-8 px-5 py-8 sm:px-6">
        {organizations.data && (
          <CreateUserPanel
            organizations={organizations.data}
            csrfToken={session.csrf_token}
            onCreated={async () => {
              setFeedback("Usuario creado con contraseña temporal.");
              await queryClient.invalidateQueries({ queryKey: usersQueryKey });
            }}
          />
        )}

        {feedback && (
          <p
            role="status"
            className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
          >
            {feedback}
          </p>
        )}
        {(loadError || actionError) && (
          <p
            role="alert"
            className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          >
            {errorMessage(loadError ?? actionError)}
          </p>
        )}

        <section aria-labelledby="usuarios-registrados">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-cyan-800">Cuentas locales</p>
              <h2
                id="usuarios-registrados"
                className="mt-1 text-2xl font-bold text-slate-950"
              >
                Usuarios registrados
              </h2>
            </div>
            {users.isFetching && (
              <span role="status" className="text-sm text-slate-500">
                Actualizando…
              </span>
            )}
          </div>

          {users.isPending || organizations.isPending ? (
            <p role="status" className="mt-5 text-slate-600">
              Cargando usuarios…
            </p>
          ) : users.data?.length === 0 ? (
            <p className="mt-5 rounded-2xl border border-slate-200 bg-white p-6 text-slate-600">
              Todavía no hay usuarios registrados.
            </p>
          ) : (
            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              {users.data?.map((user) => (
                <article
                  key={user.id}
                  className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="break-all font-semibold text-slate-950">
                        {user.email}
                      </h3>
                      <p className="mt-1 text-sm text-slate-600">
                        {roleLabels[user.rol]}
                      </p>
                    </div>
                    <StatusBadge active={user.activo} />
                  </div>
                  <dl className="mt-4 space-y-2 text-sm">
                    <div>
                      <dt className="inline text-slate-500">Organización: </dt>
                      <dd className="inline font-medium text-slate-800">
                        {user.organizacion?.nombre ?? "Sin organización"}
                      </dd>
                    </div>
                    <div>
                      <dt className="inline text-slate-500">Contraseña: </dt>
                      <dd className="inline font-medium text-slate-800">
                        {user.requiere_cambio_password
                          ? "Cambio pendiente"
                          : "Vigente"}
                      </dd>
                    </div>
                  </dl>
                  <div className="mt-5 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => setEditingUser(user)}
                      className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      onClick={() => setResettingUser(user)}
                      disabled={user.id === session.usuario.id}
                      className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-45"
                    >
                      Restablecer contraseña
                    </button>
                    <button
                      type="button"
                      onClick={() => changeStatus(user)}
                      disabled={
                        statusMutation.isPending ||
                        (user.id === session.usuario.id && user.activo)
                      }
                      className={`rounded-lg px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-45 ${
                        user.activo
                          ? "bg-red-50 text-red-800 hover:bg-red-100"
                          : "bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
                      }`}
                    >
                      {user.activo ? "Desactivar" : "Reactivar"}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>

      {editingUser && organizations.data && (
        <EditUserPanel
          user={editingUser}
          organizations={organizations.data}
          currentUserId={session.usuario.id}
          csrfToken={session.csrf_token}
          onClose={() => setEditingUser(null)}
          onUpdated={async () => {
            setEditingUser(null);
            setFeedback("Usuario actualizado.");
            await queryClient.invalidateQueries({ queryKey: usersQueryKey });
            if (editingUser.id === session.usuario.id) {
              await queryClient.invalidateQueries({ queryKey: sessionQueryKey });
            }
          }}
        />
      )}
      {resettingUser && (
        <ResetPasswordPanel
          user={resettingUser}
          csrfToken={session.csrf_token}
          onClose={() => setResettingUser(null)}
          onReset={async () => {
            setResettingUser(null);
            setFeedback("Contraseña temporal asignada.");
            await queryClient.invalidateQueries({ queryKey: usersQueryKey });
          }}
        />
      )}
    </main>
  );
}

function StatusBadge({ active }: { active: boolean }): ReactElement {
  return (
    <span
      className={`rounded-full px-3 py-1 text-xs font-bold ${
        active
          ? "bg-emerald-100 text-emerald-900"
          : "bg-slate-200 text-slate-700"
      }`}
    >
      {active ? "Activo" : "Inactivo"}
    </span>
  );
}

function roleOptions(): ReactElement[] {
  return roles.map((role) => (
    <option key={role} value={role}>
      {roleLabels[role]}
    </option>
  ));
}

function matchingOrganizations(
  organizations: Organization[],
  role: Role,
): Organization[] {
  const type = organizationTypeByRole[role];
  return type
    ? organizations.filter((organization) => organization.tipo === type)
    : [];
}

function hasCompatibleOrganization(
  organizations: Organization[],
  role: Role,
  organizationId: string,
): boolean {
  if (!organizationTypeByRole[role]) return true;
  return matchingOrganizations(organizations, role).some(
    (organization) => String(organization.id) === organizationId,
  );
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "No pudimos completar la operación. Intentá nuevamente.";
}

interface CreateUserPanelProps {
  organizations: Organization[];
  csrfToken: string;
  onCreated: () => Promise<void>;
}

function CreateUserPanel({
  organizations,
  csrfToken,
  onCreated,
}: CreateUserPanelProps): ReactElement {
  const {
    register,
    handleSubmit,
    control,
    reset,
    setError,
    formState: { errors },
  } = useForm<CreateUserForm>({
    resolver: zodResolver(createUserSchema),
    defaultValues: {
      email: "",
      password: "",
      rol: "AUDITOR_DIRECTIVO",
      organizacion_id: "",
    },
  });
  const role = useWatch({ control, name: "rol" });
  const mutation = useMutation({
    mutationFn: (values: CreateUserForm) => createUser(values, csrfToken),
    onSuccess: async () => {
      reset();
      await onCreated();
    },
  });
  const submit = (values: CreateUserForm): void => {
    if (
      !hasCompatibleOrganization(
        organizations,
        values.rol,
        values.organizacion_id,
      )
    ) {
      setError("organizacion_id", {
        message: "Seleccioná una organización para este rol.",
      });
      return;
    }
    mutation.mutate(values);
  };

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
      <h2 className="text-xl font-bold text-slate-950">Crear usuario</h2>
      <p className="mt-2 text-sm leading-6 text-slate-600">
        La contraseña será temporal y deberá cambiarse en el primer acceso.
      </p>
      <form
        className="mt-5 grid gap-4 md:grid-cols-2"
        onSubmit={(event) => void handleSubmit(submit)(event)}
        noValidate
      >
        <FormField label="Correo electrónico" error={errors.email?.message}>
          <input
            type="email"
            autoComplete="off"
            className="form-input"
            {...register("email")}
          />
        </FormField>
        <FormField label="Contraseña temporal" error={errors.password?.message}>
          <input
            type="password"
            autoComplete="new-password"
            className="form-input"
            {...register("password")}
          />
        </FormField>
        <FormField label="Rol" error={errors.rol?.message}>
          <select className="form-input" {...register("rol")}>
            {roleOptions()}
          </select>
        </FormField>
        <FormField label="Organización" error={errors.organizacion_id?.message}>
          <select className="form-input" {...register("organizacion_id")}>
            <option value="">
              {organizationTypeByRole[role]
                ? "Seleccionar organización"
                : "No corresponde"}
            </option>
            {matchingOrganizations(organizations, role).map((organization) => (
              <option key={organization.id} value={organization.id}>
                {organization.nombre}
              </option>
            ))}
          </select>
        </FormField>
        {mutation.isError && (
          <p role="alert" className="text-sm text-red-700 md:col-span-2">
            {errorMessage(mutation.error)}
          </p>
        )}
        <div className="md:col-span-2 md:text-right">
          <button
            type="submit"
            disabled={mutation.isPending}
            className="rounded-xl bg-cyan-700 px-5 py-3 text-sm font-bold text-white hover:bg-cyan-800 disabled:opacity-60"
          >
            {mutation.isPending ? "Creando…" : "Crear usuario"}
          </button>
        </div>
      </form>
    </section>
  );
}

interface EditUserPanelProps {
  user: ManagedUser;
  organizations: Organization[];
  currentUserId: number;
  csrfToken: string;
  onClose: () => void;
  onUpdated: () => Promise<void>;
}

function EditUserPanel({
  user,
  organizations,
  currentUserId,
  csrfToken,
  onClose,
  onUpdated,
}: EditUserPanelProps): ReactElement {
  const {
    register,
    handleSubmit,
    control,
    setError,
    formState: { errors },
  } = useForm<EditUserForm>({
    resolver: zodResolver(editUserSchema),
    defaultValues: {
      email: user.email,
      rol: user.rol,
      organizacion_id: String(user.organizacion?.id ?? ""),
    },
  });
  const role = useWatch({ control, name: "rol" });
  const mutation = useMutation({
    mutationFn: (values: EditUserForm) =>
      updateUser(user.id, values, csrfToken),
    onSuccess: onUpdated,
  });
  const submit = (values: EditUserForm): void => {
    if (
      !hasCompatibleOrganization(
        organizations,
        values.rol,
        values.organizacion_id,
      )
    ) {
      setError("organizacion_id", {
        message: "Seleccioná una organización para este rol.",
      });
      return;
    }
    mutation.mutate(values);
  };

  return (
    <Overlay title={`Editar ${user.email}`} onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={(event) => void handleSubmit(submit)(event)}
        noValidate
      >
        <FormField label="Correo electrónico" error={errors.email?.message}>
          <input type="email" className="form-input" {...register("email")} />
        </FormField>
        <FormField label="Rol" error={errors.rol?.message}>
          {user.id === currentUserId ? (
            <>
              <input type="hidden" {...register("rol")} />
              <span className="form-input block bg-slate-100">
                {roleLabels[user.rol]}
              </span>
            </>
          ) : (
            <select className="form-input" {...register("rol")}>
              {roleOptions()}
            </select>
          )}
        </FormField>
        <FormField label="Organización" error={errors.organizacion_id?.message}>
          <select className="form-input" {...register("organizacion_id")}>
            <option value="">
              {organizationTypeByRole[role]
                ? "Seleccionar organización"
                : "No corresponde"}
            </option>
            {matchingOrganizations(organizations, role).map((organization) => (
              <option key={organization.id} value={organization.id}>
                {organization.nombre}
              </option>
            ))}
          </select>
        </FormField>
        {mutation.isError && (
          <p role="alert" className="text-sm text-red-700">
            {errorMessage(mutation.error)}
          </p>
        )}
        <PanelActions
          pending={mutation.isPending}
          submitLabel="Guardar cambios"
          onClose={onClose}
        />
      </form>
    </Overlay>
  );
}

interface ResetPasswordPanelProps {
  user: ManagedUser;
  csrfToken: string;
  onClose: () => void;
  onReset: () => Promise<void>;
}

function ResetPasswordPanel({
  user,
  csrfToken,
  onClose,
  onReset,
}: ResetPasswordPanelProps): ReactElement {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ResetPasswordForm>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { password: "", confirmacion: "" },
  });
  const mutation = useMutation({
    mutationFn: (values: ResetPasswordForm) =>
      resetUserPassword(user.id, values, csrfToken),
    onSuccess: onReset,
  });

  return (
    <Overlay title={`Restablecer contraseña de ${user.email}`} onClose={onClose}>
      <p className="mb-5 text-sm leading-6 text-slate-600">
        Se invalidarán sus sesiones y deberá reemplazar esta clave temporal.
      </p>
      <form
        className="space-y-4"
        onSubmit={(event) =>
          void handleSubmit((values) => mutation.mutate(values))(event)
        }
        noValidate
      >
        <FormField label="Contraseña temporal" error={errors.password?.message}>
          <input
            type="password"
            autoComplete="new-password"
            className="form-input"
            {...register("password")}
          />
        </FormField>
        <FormField
          label="Repetir contraseña temporal"
          error={errors.confirmacion?.message}
        >
          <input
            type="password"
            autoComplete="new-password"
            className="form-input"
            {...register("confirmacion")}
          />
        </FormField>
        {mutation.isError && (
          <p role="alert" className="text-sm text-red-700">
            {errorMessage(mutation.error)}
          </p>
        )}
        <PanelActions
          pending={mutation.isPending}
          submitLabel="Asignar contraseña"
          onClose={onClose}
        />
      </form>
    </Overlay>
  );
}

function FormField({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: ReactElement;
}): ReactElement {
  return (
    <label className="block text-sm font-semibold text-slate-800">
      {label}
      <span className="mt-2 block">{children}</span>
      {error && <span className="mt-2 block text-red-700">{error}</span>}
    </label>
  );
}

function Overlay({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactElement | ReactElement[];
}): ReactElement {
  return (
    <div className="fixed inset-0 z-10 grid place-items-center overflow-y-auto bg-slate-950/55 p-4">
      <section
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl"
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <h2 className="text-xl font-bold text-slate-950">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="rounded-lg px-2 py-1 text-slate-500 hover:bg-slate-100"
          >
            ✕
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

function PanelActions({
  pending,
  submitLabel,
  onClose,
}: {
  pending: boolean;
  submitLabel: string;
  onClose: () => void;
}): ReactElement {
  return (
    <div className="flex flex-col-reverse gap-3 pt-2 sm:flex-row sm:justify-end">
      <button
        type="button"
        onClick={onClose}
        className="rounded-xl border border-slate-300 px-4 py-2.5 text-sm font-semibold text-slate-700"
      >
        Cancelar
      </button>
      <button
        type="submit"
        disabled={pending}
        className="rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-60"
      >
        {pending ? "Guardando…" : submitLabel}
      </button>
    </div>
  );
}
