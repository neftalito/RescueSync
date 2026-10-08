import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactElement } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";

import { ApiError } from "../api/client";
import {
  createOrganization,
  deactivateOrganization,
  getOrganizations,
  linkNationalOrganization,
  organizationsQueryKey,
  reactivateOrganization,
  updateOrganization,
} from "../api/organizations";
import type { Session } from "../schemas/auth";
import { vinculoFormSchema, type VinculoForm } from "../schemas/inventario";
import {
  createOrganizationSchema,
  editOrganizationSchema,
  organizationTypeLabels,
  organizationTypes,
  type CreateOrganizationForm,
  type EditOrganizationForm,
  type Organization,
} from "../schemas/organizations";

interface OrganizationsPageProps {
  session: Session;
}

export function OrganizationsPage({
  session,
}: OrganizationsPageProps): ReactElement {
  const queryClient = useQueryClient();
  const [feedback, setFeedback] = useState<string | null>(null);
  const [editingOrganization, setEditingOrganization] =
    useState<Organization | null>(null);
  const organizations = useQuery({
    queryKey: organizationsQueryKey,
    queryFn: getOrganizations,
  });
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreateOrganizationForm>({
    resolver: zodResolver(createOrganizationSchema),
    defaultValues: { nombre: "", tipo: "ONG" },
  });
  const mutation = useMutation({
    mutationFn: (values: CreateOrganizationForm) =>
      createOrganization(values, session.csrf_token),
    onSuccess: async () => {
      reset();
      setFeedback("Organización creada.");
      await queryClient.invalidateQueries({ queryKey: organizationsQueryKey });
    },
  });
  const statusMutation = useMutation({
    mutationFn: async ({
      organization,
      active,
    }: {
      organization: Organization;
      active: boolean;
    }) => {
      if (active) {
        return reactivateOrganization(organization.id, session.csrf_token);
      }
      await deactivateOrganization(organization.id, session.csrf_token);
      return null;
    },
    onSuccess: async (_, variables) => {
      setFeedback(
        variables.active
          ? "Organización recuperada. Sus usuarios permanecen inactivos."
          : "Organización eliminada de forma lógica y usuarios relacionados desactivados.",
      );
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: organizationsQueryKey }),
        queryClient.invalidateQueries({ queryKey: ["users"] }),
      ]);
    },
  });

  const submit = (values: CreateOrganizationForm): void => {
    setFeedback(null);
    mutation.mutate(values);
  };

  const changeStatus = (organization: Organization): void => {
    if (
      organization.activa &&
      !window.confirm(
        `¿Eliminar ${organization.nombre}? La baja será lógica y también se desactivarán todos sus usuarios.`,
      )
    ) {
      return;
    }
    setFeedback(null);
    statusMutation.mutate({
      organization,
      active: !organization.activa,
    });
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
              Administración de organizaciones
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
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
          <h2 className="text-xl font-bold text-slate-950">
            Crear organización
          </h2>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Registrá un municipio, centro coordinador u ONG para poder asignarle
            usuarios.
          </p>
          <form
            className="mt-5 grid gap-4 md:grid-cols-2"
            onSubmit={(event) => void handleSubmit(submit)(event)}
            noValidate
          >
            <label className="block text-sm font-semibold text-slate-800">
              Nombre
              <input
                type="text"
                autoComplete="organization"
                className="form-input mt-2"
                aria-invalid={errors.nombre ? "true" : undefined}
                {...register("nombre")}
              />
              {errors.nombre && (
                <span className="mt-2 block text-red-700">
                  {errors.nombre.message}
                </span>
              )}
            </label>
            <label className="block text-sm font-semibold text-slate-800">
              Tipo
              <select className="form-input mt-2" {...register("tipo")}>
                {organizationTypes.map((type) => (
                  <option key={type} value={type}>
                    {organizationTypeLabels[type]}
                  </option>
                ))}
              </select>
            </label>
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
                {mutation.isPending ? "Creando…" : "Crear organización"}
              </button>
            </div>
          </form>
        </section>

        {feedback && (
          <p
            role="status"
            className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
          >
            {feedback}
          </p>
        )}
        {statusMutation.isError && (
          <p
            role="alert"
            className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          >
            {errorMessage(statusMutation.error)}
          </p>
        )}

        <section aria-labelledby="organizaciones-registradas">
          <div className="flex items-end justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-cyan-800">
                Directorio local
              </p>
              <h2
                id="organizaciones-registradas"
                className="mt-1 text-2xl font-bold text-slate-950"
              >
                Organizaciones registradas
              </h2>
            </div>
            {organizations.isFetching && !organizations.isPending && (
              <span role="status" className="text-sm text-slate-500">
                Actualizando…
              </span>
            )}
          </div>

          {organizations.isPending ? (
            <p role="status" className="mt-5 text-slate-600">
              Cargando organizaciones…
            </p>
          ) : organizations.isError ? (
            <p
              role="alert"
              className="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
            >
              {errorMessage(organizations.error)}
            </p>
          ) : organizations.data.length === 0 ? (
            <p className="mt-5 rounded-2xl border border-slate-200 bg-white p-6 text-slate-600">
              Todavía no hay organizaciones registradas.
            </p>
          ) : (
            <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {organizations.data.map((organization) => (
                <article
                  key={organization.id}
                  className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
                >
                  <p className="text-xs font-bold tracking-[0.12em] text-cyan-800 uppercase">
                    {organizationTypeLabels[organization.tipo]}
                  </p>
                  <h3 className="mt-2 font-semibold text-slate-950">
                    {organization.nombre}
                  </h3>
                  <p className="mt-2 text-sm text-slate-600">
                    {organization.activa ? "Activa" : "Inactiva"}
                  </p>
                  {organization.tipo === "ONG" && (
                    <p className="mt-2 break-all text-xs text-slate-500">
                      {organization.ong_nacional_id
                        ? `UUID nacional: ${organization.ong_nacional_id}`
                        : "Sin vinculación nacional"}
                    </p>
                  )}
                  <div className="mt-5 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => setEditingOrganization(organization)}
                      className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                    >
                      Editar
                    </button>
                    <button
                      type="button"
                      disabled={statusMutation.isPending}
                      onClick={() => changeStatus(organization)}
                      className={`rounded-lg px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-45 ${
                        organization.activa
                          ? "bg-red-50 text-red-800 hover:bg-red-100"
                          : "bg-emerald-50 text-emerald-800 hover:bg-emerald-100"
                      }`}
                    >
                      {organization.activa ? "Eliminar" : "Recuperar"}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>

      {editingOrganization && (
        <EditOrganizationPanel
          organization={editingOrganization}
          csrfToken={session.csrf_token}
          onClose={() => setEditingOrganization(null)}
          onUpdated={async () => {
            setEditingOrganization(null);
            setFeedback("Organización actualizada.");
            await queryClient.invalidateQueries({
              queryKey: organizationsQueryKey,
            });
          }}
        />
      )}
    </main>
  );
}

interface EditOrganizationPanelProps {
  organization: Organization;
  csrfToken: string;
  onClose: () => void;
  onUpdated: () => Promise<void>;
}

function EditOrganizationPanel({
  organization,
  csrfToken,
  onClose,
  onUpdated,
}: EditOrganizationPanelProps): ReactElement {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<EditOrganizationForm>({
    resolver: zodResolver(editOrganizationSchema),
    defaultValues: {
      nombre: organization.nombre,
      tipo: organization.tipo,
    },
  });
  const mutation = useMutation({
    mutationFn: (values: EditOrganizationForm) =>
      updateOrganization(organization.id, values, csrfToken),
    onSuccess: onUpdated,
  });

  return (
    <div className="fixed inset-0 z-10 grid place-items-center overflow-y-auto bg-slate-950/55 p-4">
      <section
        role="dialog"
        aria-modal="true"
        aria-label={`Editar ${organization.nombre}`}
        className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl"
      >
        <div className="mb-5 flex items-start justify-between gap-4">
          <h2 className="text-xl font-bold text-slate-950">
            Editar organización
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="rounded-lg px-2 py-1 text-slate-500 hover:bg-slate-100"
          >
            ✕
          </button>
        </div>
        <form
          className="space-y-4"
          onSubmit={(event) =>
            void handleSubmit((values) => mutation.mutate(values))(event)
          }
          noValidate
        >
          <label className="block text-sm font-semibold text-slate-800">
            Nombre
            <input
              type="text"
              className="form-input mt-2"
              aria-invalid={errors.nombre ? "true" : undefined}
              {...register("nombre")}
            />
            {errors.nombre && (
              <span className="mt-2 block text-red-700">
                {errors.nombre.message}
              </span>
            )}
          </label>
          <label className="block text-sm font-semibold text-slate-800">
            Tipo
            <select className="form-input mt-2" {...register("tipo")}>
              {organizationTypes.map((type) => (
                <option key={type} value={type}>
                  {organizationTypeLabels[type]}
                </option>
              ))}
            </select>
          </label>
          {mutation.isError && (
            <p role="alert" className="text-sm text-red-700">
              {errorMessage(mutation.error)}
            </p>
          )}
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
              disabled={mutation.isPending}
              className="rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-60"
            >
              {mutation.isPending ? "Guardando…" : "Guardar cambios"}
            </button>
          </div>
        </form>
        {organization.tipo === "ONG" && (
          <NationalLinkForm
            organization={organization}
            csrfToken={csrfToken}
            onUpdated={onUpdated}
          />
        )}
      </section>
    </div>
  );
}

function errorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "No pudimos completar la operación. Intentá nuevamente.";
}

function NationalLinkForm({
  organization,
  csrfToken,
  onUpdated,
}: {
  organization: Organization;
  csrfToken: string;
  onUpdated: () => Promise<void>;
}): ReactElement {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<VinculoForm>({
    resolver: zodResolver(vinculoFormSchema),
    defaultValues: { ong_nacional_id: organization.ong_nacional_id ?? "" },
  });
  const mutation = useMutation({
    mutationFn: (datos: VinculoForm) =>
      linkNationalOrganization(
        organization.id,
        datos.ong_nacional_id,
        csrfToken,
      ),
    onSuccess: onUpdated,
  });
  return (
    <form
      className="mt-6 space-y-3 border-t border-slate-200 pt-5"
      noValidate
      onSubmit={(event) =>
        void handleSubmit((datos) => mutation.mutate(datos))(event)
      }
    >
      <label className="block text-sm font-semibold">
        UUID de la ONG nacional
        <input className="form-input mt-2" {...register("ong_nacional_id")} />
        {errors.ong_nacional_id && (
          <span role="alert" className="text-red-800">
            {errors.ong_nacional_id.message}
          </span>
        )}
      </label>
      <p className="text-sm text-slate-600">
        Ingresá el UUID del registro nacional verificado. Vacío elimina la
        vinculación. Guardar desconecta las cuentas nacionales de sus
        representantes.
      </p>
      {mutation.isError && (
        <p role="alert" className="text-red-800">
          {errorMessage(mutation.error)}
        </p>
      )}
      <button
        className="rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50"
        disabled={mutation.isPending}
      >
        {mutation.isPending ? "Guardando…" : "Guardar vinculación nacional"}
      </button>
    </form>
  );
}
