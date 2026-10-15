import { zodResolver } from "@hookform/resolvers/zod";
import { useState, type ReactElement } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router";
import { ApiError } from "../api/client";
import { CertificacionesOngPanel } from "../components/CertificacionesOng";
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

const boton =
  "rounded-xl bg-cyan-700 px-4 py-2.5 text-sm font-bold text-white hover:bg-cyan-800 disabled:opacity-50";
const panel = "rounded-2xl border border-slate-200 bg-white p-5 shadow-sm";
function mensaje(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "No pudimos completar la operación. Intentá nuevamente.";
}
function ErrorMensaje({ error }: { error: unknown }): ReactElement | null {
  return error ? (
    <p role="alert" className="mt-3 text-sm text-red-800">
      {mensaje(error)}
    </p>
  ) : null;
}

export function MisRecursosPage({
  session,
}: {
  session: Session;
}): ReactElement {
  const inventario = useInventarioNacional(session);
  const [feedback, setFeedback] = useState("");
  const [editando, setEditando] = useState<Recurso | null>(null);
  const [mostrarRegistro, setMostrarRegistro] = useState(false);
  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 sm:px-6">
      <div className="mx-auto max-w-6xl space-y-6">
        <Link to="/" className="font-semibold text-cyan-800">
          ← Volver al inicio
        </Link>
        <header>
          <p className="text-sm font-semibold text-cyan-800">
            {session.usuario.organizacion?.nombre}
          </p>
          <h1 className="mt-1 text-3xl font-bold text-slate-950">
            Mis recursos
          </h1>
          <p className="mt-2 text-slate-600">
            Registrá recursos y actualizá el inventario de tu ONG en el Sistema
            Nacional y consultá tus certificaciones y capacidades habilitadas.
          </p>
        </header>
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
              className={`${boton} mt-4`}
              onClick={() => void inventario.conexion.refetch()}
            >
              Reintentar
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
                  Ya podés gestionar tus recursos. Las certificaciones y la
                  habilitación institucional se revisan por separado.
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
                className={`${boton} mt-4`}
                onClick={() => setMostrarRegistro(true)}
              >
                Registrar ONG en el Sistema Nacional
              </button>
            )}
            <button
              type="button"
              className="mt-4 block rounded-xl border border-slate-300 px-4 py-2.5"
              disabled={inventario.conexion.isFetching}
              onClick={() => void inventario.conexion.refetch()}
            >
              Volver a consultar vinculación
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
            <button type="button" className={`${boton} mt-4`}
              onClick={() => void inventario.conexion.refetch()}>
              Volver a consultar acceso
            </button>
          </section>
        ) : (
          <>
            <section
              className={`${panel} flex flex-wrap items-center justify-between gap-3`}
            >
              <div>
                <h2 className="font-bold text-slate-900">
                  Acceso nacional automático
                </h2>
                <p className="mt-1 text-sm text-slate-600">
                  Las cantidades comprometidas y disponibles se calculan
                  automáticamente.
                </p>
              </div>
            </section>
            <CertificacionesOngPanel
              perfil={inventario.certificaciones}
              catalogo={inventario.catalogoCertificaciones}
            />
            <section aria-labelledby="nuevo-recurso" className={panel}>
              <h2 id="nuevo-recurso" className="text-xl font-bold">
                Registrar recurso
              </h2>
              {inventario.capacidades.isPending ? (
                <p role="status">Cargando capacidades…</p>
              ) : inventario.capacidades.isError ? (
                <>
                  <ErrorMensaje error={inventario.capacidades.error} />
                  <button
                    className={`${boton} mt-3`}
                    onClick={() => void inventario.capacidades.refetch()}
                  >
                    Reintentar capacidades
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
            <section aria-labelledby="inventario">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 id="inventario" className="text-2xl font-bold">
                  Inventario de mi ONG
                </h2>
                <button
                  type="button"
                  disabled={inventario.recursos.isFetching}
                  className={boton}
                  onClick={() => {
                    setEditando(null);
                    void inventario.actualizar();
                  }}
                >
                  Actualizar listado
                </button>
              </div>
              {inventario.recursos.isPending ? (
                <p role="status" className="mt-4">
                  Cargando recursos…
                </p>
              ) : inventario.recursos.isError ? (
                <ErrorMensaje error={inventario.recursos.error} />
              ) : inventario.recursos.data.length === 0 ? (
                <p className={`${panel} mt-4 text-slate-600`}>
                  Tu ONG todavía no tiene recursos registrados.
                </p>
              ) : (
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  {inventario.recursos.data.map((recurso) => (
                    <article key={recurso.id} className={panel}>
                      <p className="text-xs font-bold text-cyan-800">
                        {recurso.codigoInterno} · {recurso.capacidad}
                      </p>
                      <h3 className="mt-2 text-lg font-bold">
                        {recurso.nombre}
                      </h3>
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
                        className={boton}
                        onClick={() => {
                          inventario.editar.reset();
                          setEditando(recurso);
                          setFeedback("");
                        }}
                      >
                        Editar {recurso.codigoInterno}
                      </button>
                    </article>
                  ))}
                </div>
              )}
            </section>
            {editando && (
              <section className={panel} aria-labelledby="editar-recurso">
                <h2 id="editar-recurso" className="text-xl font-bold">
                  Editar cantidad: {editando.nombre}
                </h2>
                <CantidadFormView
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
              </section>
            )}
          </>
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
          {...register("emailContacto")}
        />
        {errors.emailContacto && (
          <span role="alert">{errors.emailContacto.message}</span>
        )}
      </label>
      <ErrorMensaje error={error} />
      <div className="flex flex-wrap gap-3">
        <button className={boton} disabled={pendiente}>
          {pendiente ? "Registrando…" : "Crear registro nacional"}
        </button>
        <button
          type="button"
          className="rounded-xl border border-slate-300 px-4 py-2.5"
          disabled={pendiente}
          onClick={onCancel}
        >
          Cancelar registro
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
        Código interno
        <input className="form-input mt-2" {...register("codigoInterno")} />
        {errors.codigoInterno && (
          <span role="alert">{errors.codigoInterno.message}</span>
        )}
      </label>
      <label className="text-sm font-semibold">
        Nombre del recurso
        <input className="form-input mt-2" {...register("nombre")} />
        {errors.nombre && <span role="alert">{errors.nombre.message}</span>}
      </label>
      <label className="text-sm font-semibold">
        Cantidad total
        <input
          className="form-input mt-2"
          inputMode="decimal"
          {...register("cantidadTotal")}
        />
        {errors.cantidadTotal && (
          <span role="alert">{errors.cantidadTotal.message}</span>
        )}
      </label>
      <div className="sm:col-span-2">
        <ErrorMensaje error={error} />
        <button className={boton} disabled={pendiente}>
          {pendiente ? "Guardando…" : "Registrar recurso"}
        </button>
      </div>
    </form>
  );
}

function CantidadFormView({
  recurso,
  pendiente,
  error,
  onSubmit,
  onCancel,
}: {
  recurso: Recurso;
  pendiente: boolean;
  error: unknown;
  onSubmit: (cantidad: string) => Promise<void>;
  onCancel: () => void;
}): ReactElement {
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
          {...register("cantidadTotal")}
        />
        {errors.cantidadTotal && (
          <span role="alert">{errors.cantidadTotal.message}</span>
        )}
      </label>
      <ErrorMensaje error={error} />
      <div className="flex flex-wrap gap-3">
        <button className={boton} disabled={pendiente}>
          {pendiente ? "Guardando…" : "Guardar cantidad"}
        </button>
        <button
          type="button"
          className="rounded-xl border border-slate-300 px-4 py-2.5"
          disabled={pendiente}
          onClick={onCancel}
        >
          Cancelar
        </button>
      </div>
    </form>
  );
}
