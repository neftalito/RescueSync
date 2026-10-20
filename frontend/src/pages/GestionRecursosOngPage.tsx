import { ListadoLocal } from "../components/ListadoProgresivo";
import { zodResolver } from "@hookform/resolvers/zod";
import { useLayoutEffect, useRef, useState, type ReactElement } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";
import { ActionIcon } from "../components/ActionIcon";
import { ApiError } from "../api/client";
import { PerfilCompetenciaPanel } from "../components/PerfilCompetencia";
import { useInventarioNacional } from "../hooks/useInventarioNacional";
import type { Session } from "../schemas/auth";
import {
  cantidadEnMiles,
  cantidadFormSchema,
  recursoFormSchema,
  registroNacionalFormSchema,
  type CantidadForm,
  type Capacidad,
  type Recurso,
  type RecursoForm,
  type RegistroNacionalForm,
} from "../schemas/inventario";

const panel = "rounded-2xl border border-slate-200 bg-white p-5 shadow-sm";
function mensaje(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "No pudimos completar la operación. Intentá nuevamente.";
}
function ErrorMensaje({ error }: { error: unknown; }): ReactElement | null {
  return error ? (
    <p role="alert" className="mt-3 text-sm text-red-800">
      {mensaje(error)}
    </p>
  ) : null;
}

export function InventarioOngPage({ session }: { session: Session; }): ReactElement {
  return <GestionRecursosOngPage session={session} vista="inventario" />;
}

export function PerfilCompetenciaOngPage({
  session,
}: {
  session: Session;
}): ReactElement {
  return <GestionRecursosOngPage session={session} vista="perfil" />;
}

function GestionRecursosOngPage({
  session,
  vista,
}: {
  session: Session;
  vista: "inventario" | "perfil";
}): ReactElement {
  const inventario = useInventarioNacional(session, vista);
  const [feedback, setFeedback] = useState("");
  const [editando, setEditando] = useState<Recurso | null>(null);
  const [mostrarRegistro, setMostrarRegistro] = useState(false);
  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div>
            <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
              RescueSync
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-950">
              {vista === "perfil"
                ? "Perfil de competencia de mi ONG"
                : "Inventario de mi ONG"}
            </h1>
          </div>
          <nav aria-label="Navegación de recursos" className="flex flex-wrap gap-3">
            <Link
              to="/mis-recursos"
              className="action-button action-icon"
              title="Volver a Mis recursos"
            >
              <ActionIcon name="back" />
              <span className="sr-only">Volver a Mis recursos</span>
            </Link>
            <Link
              to="/"
              className="action-button action-icon"
              title="Volver al inicio"
            >
              <ActionIcon name="home" />
              <span className="sr-only">Volver al inicio</span>
            </Link>
          </nav>
        </div>
      </header>

      <div className="mx-auto max-w-6xl space-y-6 px-5 py-8 sm:px-6">
        <div>
          <p className="text-sm font-semibold text-cyan-800">
            {session.usuario.organizacion?.nombre}
          </p>
          <p className="mt-2 max-w-3xl text-slate-600">
            {vista === "perfil"
              ? "Analizá las capacidades y cantidades declaradas por tu ONG."
              : "Registrá recursos y actualizá el inventario de tu ONG en el Sistema Nacional."}
          </p>
        </div>
        {feedback && (
          <p
            role="status"
            className="rounded-xl bg-emerald-50 p-4 text-emerald-900"
          >
            {feedback}
          </p>
        )}
        {inventario.conexion.isPending ? (
          <p role="status">Consultando conexión…</p>
        ) : inventario.conexion.isError ? (
          <section className={panel}>
            <ErrorMensaje error={inventario.conexion.error} />
            <button
              type="button"
              className="action-button action-icon mt-4"
              onClick={() => void inventario.conexion.refetch()}
              title="Reintentar"
            >
              <ActionIcon name="refresh" />
              <span className="sr-only">Reintentar</span>
            </button>
          </section>
        ) : !inventario.conexion.data.vinculada ? (
          <section className={panel}>
            <h2 className="text-xl font-bold">Vinculación pendiente</h2>
            <p className="mt-2 text-slate-600">
              Completá el registro para activar el acceso nacional de tu ONG.
              Si ya existe un registro nacional anterior, pedí al administrador
              que revise su vinculación.
            </p>
            {inventario.registrar.data ? (
              <div
                role="status"
                className="mt-4 rounded-xl bg-emerald-50 p-4 text-emerald-900"
              >
                <p className="font-semibold">ONG registrada en estado pendiente.</p>
                <p className="mt-2">
                  El vínculo y el acceso nacional ya están configurados.
                  Tu identificador nacional es:
                </p>
                <p className="mt-2 break-all font-mono">
                  {inventario.registrar.data.id}
                </p>
                <p className="mt-2">
                  Ya podés gestionar tus recursos y presentar ofertas.
                </p>
              </div>
            ) : mostrarRegistro ? (
              <RegistroNacionalFormView
                pendiente={inventario.registrar.isPending}
                error={inventario.registrar.error}
                onSubmit={async (datos) => {
                  await inventario.registrar.mutateAsync(datos);
                }}
                onCancel={() => setMostrarRegistro(false)}
              />
            ) : (
              <button
                type="button"
                className="action-button action-primary mt-4"
                onClick={() => setMostrarRegistro(true)}
              >
                Registrar ONG en el Sistema Nacional
              </button>
            )}
            <button
              type="button"
              className="action-button action-icon mt-4"
              disabled={inventario.conexion.isFetching}
              onClick={() => void inventario.conexion.refetch()}
              title="Volver a consultar vinculación"
            >
              <ActionIcon name="refresh" />
              <span className="sr-only">Volver a consultar vinculación</span>
            </button>
          </section>
        ) : inventario.conexion.data.estado !== "LISTA" ? (
          <section className={panel}>
            <h2 className="text-xl font-bold">
              {inventario.conexion.data.estado === "SIN_CONFIGURAR"
                ? "Acceso nacional pendiente"
                : "El acceso nacional requiere revisión"}
            </h2>
            <p className="mt-2 text-slate-600">
              Pedile a un administrador que revise el acceso nacional de tu ONG.
              Tu sesión de RescueSync continúa activa.
            </p>
            <button
              type="button"
              className="action-button action-icon mt-4"
              onClick={() => void inventario.conexion.refetch()}
              title="Volver a consultar acceso"
            >
              <ActionIcon name="refresh" />
              <span className="sr-only">Volver a consultar acceso</span>
            </button>
          </section>
        ) : vista === "perfil" ? (
          <PerfilCompetenciaPanel
            perfil={inventario.perfil}
          />
        ) : (
          <section aria-labelledby="inventario" className={panel}>
            <h2 id="inventario" className="text-xl font-bold text-slate-950">
              Recursos de mi ONG
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              Registrá recursos y actualizá sus cantidades. Los totales
              comprometidos y disponibles se calculan automáticamente.
            </p>
            <section
              aria-labelledby="nuevo-recurso"
              className="mt-6 border-t border-slate-200 pt-6"
            >
              <h3 id="nuevo-recurso" className="text-xl font-bold">
                Registrar recurso
              </h3>
              {inventario.capacidades.isPending ? (
                <p role="status">Cargando capacidades…</p>
              ) : inventario.capacidades.isError ? (
                <>
                  <ErrorMensaje error={inventario.capacidades.error} />
                  <button
                    className="action-button action-icon mt-3"
                    onClick={() => void inventario.capacidades.refetch()}
                    title="Reintentar capacidades"
                  >
                    <ActionIcon name="refresh" />
                    <span className="sr-only">Reintentar capacidades</span>
                  </button>
                </>
              ) : inventario.capacidades.data.length === 0 ? (
                <p className="mt-3 text-slate-600">
                  El catálogo nacional todavía no tiene capacidades activas.
                </p>
              ) : (
                <RecursoFormView
                  capacidades={inventario.capacidades.data}
                  pendiente={inventario.crear.isPending}
                  error={inventario.crear.error}
                  onSubmit={async (datos) => {
                    await inventario.crear.mutateAsync(datos);
                    setFeedback("Recurso registrado.");
                  }}
                />
              )}
            </section>
            <section
              aria-labelledby="recursos-registrados"
              className="mt-6 border-t border-slate-200 pt-6"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 id="recursos-registrados" className="text-xl font-bold">
                  Recursos registrados
                </h3>
                <button
                  type="button"
                  disabled={inventario.recursos.isFetching}
                  className="action-button action-icon"
                  onClick={() => {
                    setEditando(null);
                    void inventario.actualizar();
                  }}
                  title="Actualizar listado"
                >
                  <ActionIcon name="refresh" />
                  <span className="sr-only">Actualizar listado</span>
                </button>
              </div>
              {inventario.recursos.isPending ? (
                <p role="status" className="mt-4">
                  Cargando recursos…
                </p>
              ) : inventario.recursos.isError ? (
                <ErrorMensaje error={inventario.recursos.error} />
              ) : inventario.recursos.data.length === 0 ? (
                <p className="mt-4 rounded-xl bg-slate-50 p-4 text-slate-600">
                  Tu ONG todavía no tiene recursos registrados.
                </p>
              ) : (
                <ListadoLocal items={inventario.recursos.data} etiqueta="Recursos registrados" className="mt-4">
                  {(visibles) => (
                    <div className="mt-4 grid gap-4 md:grid-cols-2">
                      {visibles.map((recurso) => (
                        <article
                          key={recurso.id}
                          className="rounded-xl border border-slate-200 bg-slate-50 p-4"
                        >
                          <p className="text-xs font-bold text-cyan-800">
                            {recurso.codigoInterno} · {recurso.capacidad}
                          </p>
                          <h4 className="mt-2 text-lg font-bold">
                            {recurso.nombre}
                          </h4>
                          <p className="mt-1 text-sm text-slate-600">
                            Unidad: {recurso.unidad}
                            {!recurso.activo && " · Inactivo"}
                          </p>
                          <dl className="my-4 grid grid-cols-1 gap-2 text-sm sm:grid-cols-3">
                            {[
                              ["Total", recurso.cantidadTotal],
                              ["Comprometido", recurso.cantidadComprometida],
                              ["Disponible", recurso.cantidadDisponible],
                            ].map(([label, value]) => (
                              <div key={label}>
                                <dt className="text-slate-600">{label}</dt>
                                <dd className="mt-1 break-all font-bold">
                                  {value}
                                </dd>
                              </div>
                            ))}
                          </dl>
                          <button
                            type="button"
                            className="action-button action-icon"
                            onClick={() => {
                              inventario.editar.reset();
                              setEditando(recurso);
                              setFeedback("");
                            }}
                            title={`Editar ${recurso.codigoInterno}`}
                          >
                            <ActionIcon name="edit" />
                            <span className="sr-only">Editar {recurso.codigoInterno}</span>
                          </button>
                        </article>
                      ))}
                    </div>
                  )}
                </ListadoLocal>
              )}
            </section>
            {editando && (
              <EditarRecursoModal
                key={`${editando.id}:${editando.actualizadoEn}`}
                recurso={editando}
                pendiente={inventario.editar.isPending}
                error={inventario.editar.error}
                onCancel={() => setEditando(null)}
                onSubmit={async (cantidadTotal) => {
                  await inventario.editar.mutateAsync({
                    recurso: editando,
                    cantidadTotal,
                  });
                  setEditando(null);
                  setFeedback("Cantidad actualizada.");
                }}
              />
            )}
          </section>
        )}
      </div>
    </main>
  );
}

function RegistroNacionalFormView({
  pendiente,
  error,
  onSubmit,
  onCancel,
}: {
  pendiente: boolean;
  error: unknown;
  onSubmit: (datos: RegistroNacionalForm) => Promise<void>;
  onCancel: () => void;
}): ReactElement {
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<RegistroNacionalForm>({
    resolver: zodResolver(registroNacionalFormSchema),
  });
  return (
    <form
      className="mt-4 space-y-4"
      noValidate
      onSubmit={(event) =>
        void handleSubmit(async (datos) => {
          try {
            await onSubmit(datos);
            reset();
          } catch {
            // La mutación conserva el error y permite reintentar el mismo registro.
          }
        })(event)
      }
    >
      <h3 className="text-lg font-bold">Registrar mi ONG</h3>
      <p className="text-slate-600">
        Si tu ONG ya está registrada, pedí la vinculación al administrador. Para un
        registro nuevo se usará el nombre de tu organización local y se generarán
        automáticamente el identificador y el acceso nacional.
      </p>
      <label className="block text-sm font-semibold">
        Email de contacto (opcional)
        <input
          className="form-input mt-2"
          type="email"
          autoComplete="email"
          placeholder="contacto@organizacion.org"
          {...register("emailContacto")}
        />
        {errors.emailContacto && (
          <span role="alert">{errors.emailContacto.message}</span>
        )}
      </label>
      <ErrorMensaje error={error} />
      <div className="flex flex-wrap gap-3">
        <button className="action-button action-primary" disabled={pendiente}>
          {pendiente ? "Registrando…" : "Crear registro nacional"}
        </button>
        <button
          type="button"
          className="action-button action-icon"
          disabled={pendiente}
          onClick={onCancel}
          title="Cancelar registro"
        >
          <ActionIcon name="close" />
          <span className="sr-only">Cancelar registro</span>
        </button>
      </div>
    </form>
  );
}

function RecursoFormView({
  capacidades,
  pendiente,
  error,
  onSubmit,
}: {
  capacidades: Capacidad[];
  pendiente: boolean;
  error: unknown;
  onSubmit: (datos: RecursoForm) => Promise<void>;
}): ReactElement {
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<RecursoForm>({
    resolver: zodResolver(recursoFormSchema),
    defaultValues: {
      capacidadId: "",
      codigoInterno: "",
      nombre: "",
      cantidadTotal: "",
    },
  });
  return (
    <form
      className="mt-4 grid gap-4 sm:grid-cols-2"
      noValidate
      onSubmit={(event) =>
        void handleSubmit(async (datos) => {
          const capacidad = capacidades.find((c) => c.id === datos.capacidadId);
          if (
            capacidad &&
            !capacidad.admiteFracciones &&
            cantidadEnMiles(datos.cantidadTotal) % 1000n !== 0n
          ) {
            setError("cantidadTotal", {
              message: "Esta capacidad requiere cantidades enteras.",
            });
            return;
          }
          try {
            await onSubmit(datos);
            reset();
          } catch {
            /* La mutación presenta el error. */
          }
        })(event)
      }
    >
      <label className="text-sm font-semibold">
        Capacidad y unidad
        <select className="form-input mt-2" {...register("capacidadId")}>
          <option value="">Seleccioná una capacidad</option>
          {capacidades.map((c) => (
            <option key={c.id} value={c.id}>
              {c.nombre} ({c.unidad})
            </option>
          ))}
        </select>
        {errors.capacidadId && (
          <span role="alert">{errors.capacidadId.message}</span>
        )}
      </label>
      <label className="text-sm font-semibold">
        Descripción corta
        <input
          className="form-input mt-2"
          placeholder="Ej.: Ambulancia de guardia"
          maxLength={80}
          {...register("codigoInterno")}
        />
        {errors.codigoInterno && (
          <span role="alert">{errors.codigoInterno.message}</span>
        )}
      </label>
      <label className="text-sm font-semibold">
        Nombre del recurso
        <input
          className="form-input mt-2"
          placeholder="Ej.: Ambulancia equipada para rescate"
          {...register("nombre")}
        />
        {errors.nombre && <span role="alert">{errors.nombre.message}</span>}
      </label>
      <label className="text-sm font-semibold">
        Cantidad total
        <input
          className="form-input mt-2"
          inputMode="decimal"
          placeholder="Ej.: 10"
          {...register("cantidadTotal")}
        />
        {errors.cantidadTotal && (
          <span role="alert">{errors.cantidadTotal.message}</span>
        )}
      </label>
      <div className="sm:col-span-2">
        <ErrorMensaje error={error} />
        <button className="action-button action-primary" disabled={pendiente}>
          {pendiente ? "Guardando…" : "Registrar recurso"}
        </button>
      </div>
    </form>
  );
}

interface EdicionRecursoProps {
  recurso: Recurso;
  pendiente: boolean;
  error: unknown;
  onSubmit: (cantidad: string) => Promise<void>;
  onCancel: () => void;
}

function EditarRecursoModal(props: EdicionRecursoProps): ReactElement {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useLayoutEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const overflowAnterior = document.body.style.overflow;
    dialog.showModal();
    dialog.querySelector("input")?.focus();
    document.body.style.overflow = "hidden";
    return () => {
      dialog.close();
      document.body.style.overflow = overflowAnterior;
    };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      aria-modal="true"
      aria-labelledby="editar-recurso"
      aria-describedby="editar-recurso-detalle"
      className="fixed inset-0 m-auto max-h-[calc(100dvh_-_2rem)] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto rounded-2xl border border-slate-200 bg-white p-5 text-slate-950 shadow-2xl backdrop:bg-slate-950/55 sm:p-6"
      onCancel={(event) => {
        event.preventDefault();
        if (!props.pendiente) props.onCancel();
      }}
    >
      <div className="flex items-start justify-between gap-4">
        <h2 id="editar-recurso" className="min-w-0 text-xl font-bold break-words">
          Editar cantidad: {props.recurso.nombre}
        </h2>
        <button
          type="button"
          aria-label="Cerrar edición"
          disabled={props.pendiente}
          onClick={props.onCancel}
          className="action-button action-icon"
          title="Cerrar edición"
        >
          <ActionIcon name="close" />
        </button>
      </div>
      <p
        id="editar-recurso-detalle"
        className="mt-2 text-sm text-slate-600 break-words"
      >
        {props.recurso.codigoInterno} · {props.recurso.capacidad}
      </p>
      <CantidadFormView {...props} />
    </dialog>
  );
}

function CantidadFormView({
  recurso,
  pendiente,
  error,
  onSubmit,
  onCancel,
}: EdicionRecursoProps): ReactElement {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<CantidadForm>({
    resolver: zodResolver(cantidadFormSchema),
    defaultValues: { cantidadTotal: recurso.cantidadTotal },
  });
  return (
    <form
      className="mt-4 space-y-4"
      noValidate
      onSubmit={(event) =>
        void handleSubmit(async (datos) => {
          const cantidad = cantidadEnMiles(datos.cantidadTotal);
          if (!recurso.admiteFracciones && cantidad % 1000n !== 0n) {
            setError("cantidadTotal", {
              message: "Esta capacidad requiere cantidades enteras.",
            });
            return;
          }
          if (cantidad < cantidadEnMiles(recurso.cantidadComprometida)) {
            setError("cantidadTotal", {
              message: `El total debe ser al menos ${recurso.cantidadComprometida}, que ya está comprometido.`,
            });
            return;
          }
          try {
            await onSubmit(datos.cantidadTotal);
          } catch {
            /* La mutación presenta el error. */
          }
        })(event)
      }
    >
      <label className="block text-sm font-semibold">
        Nuevo total ({recurso.unidad})
        <input
          className="form-input mt-2"
          inputMode="decimal"
          disabled={pendiente}
          placeholder="Ingresá la nueva cantidad total"
          aria-invalid={errors.cantidadTotal ? "true" : undefined}
          aria-describedby={
            errors.cantidadTotal ? "editar-cantidad-error" : undefined
          }
          {...register("cantidadTotal")}
        />
        {errors.cantidadTotal && (
          <span id="editar-cantidad-error" role="alert">
            {errors.cantidadTotal.message}
          </span>
        )}
      </label>
      <ErrorMensaje error={error} />
      <div className="flex flex-wrap gap-3">
        <button
          className="action-button action-primary action-icon"
          disabled={pendiente}
          aria-busy={pendiente}
          title={pendiente ? "Guardando…" : "Guardar cantidad"}
        >
          <ActionIcon name="save" />
          <span className="sr-only">
            {pendiente ? "Guardando…" : "Guardar cantidad"}
          </span>
        </button>
        <button
          type="button"
          className="action-button action-icon"
          disabled={pendiente}
          onClick={onCancel}
          title="Cancelar"
        >
          <ActionIcon name="close" />
          <span className="sr-only">Cancelar</span>
        </button>
      </div>
    </form>
  );
}
