import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type ReactElement } from "react";
import { Link, useParams } from "react-router";
import { consultarComandos, consultarEvaluacion, consultarSeguimiento, enviarComando } from "../api/ejecucion";
import { ResumenCompetencia } from "../components/PerfilCompetencia";
import { ApiError } from "../api/client";
import type { Session } from "../schemas/auth";
import { validarSeleccion } from "../schemas/ejecucion";

export function EjecucionPage({ session }: { session: Session }): ReactElement {
  const id = Number(useParams().emergenciaId);
  const rol = session.usuario.rol;
  const esOng = rol === "REPRESENTANTE_ONG";
  const esMunicipio = rol === "OPERADOR_MUNICIPAL";
  const queryClient = useQueryClient();
  const [cantidades, setCantidades] = useState<Record<number, string>>({});
  const [motivo, setMotivo] = useState("");
  const [errorLocal, setErrorLocal] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);
  // Un fallo de transporte conserva UUID y contenido para repetir la misma intención.
  const intencion = useRef<{ contenido: string; id: string } | null>(null);
  const evaluacion = useQuery({ queryKey: ["ejecucion", id, "evaluacion"], queryFn: () => consultarEvaluacion(id), enabled: !esOng, refetchInterval: 5000 });
  const seguimiento = useQuery({ queryKey: ["ejecucion", id, "seguimiento"], queryFn: () => consultarSeguimiento(id), refetchInterval: 5000 });
  const comandos = useQuery({ queryKey: ["ejecucion", id, "comandos"], queryFn: () => consultarComandos(id), refetchInterval: 5000 });
  const mutation = useMutation({
    mutationFn: ({ ruta, body }: { ruta: string; body?: object }) => enviarComando(id, ruta, session.csrf_token, body),
    onError: (error) => {
      if (error instanceof ApiError && error.status >= 400 && error.status < 500) intencion.current = null;
    },
    onSuccess: () => {
      setMensaje("Solicitud guardada. Podés seguir su confirmación en esta pantalla.");
      setErrorLocal(null);
      intencion.current = null;
      void queryClient.invalidateQueries({ queryKey: ["ejecucion", id] });
    },
  });
  const v = evaluacion.data?.validacion;
  const bloqueada = seguimiento.data?.adjudicaciones.some(a => a.estado !== "REQUIERE_REVISION") ?? false;

  function identidad(contenido: object): string | null {
    const serializado = JSON.stringify(contenido);
    if (intencion.current && intencion.current.contenido !== serializado) {
      setErrorLocal("La respuesta anterior es incierta. Reintentá con las mismas cantidades o actualizá el seguimiento antes de cambiar la selección.");
      return null;
    }
    intencion.current ??= { contenido: serializado, id: crypto.randomUUID() };
    return intencion.current.id;
  }

  function seleccionar(): void {
    if (!evaluacion.data || !v) return;
    const error = validarSeleccion(evaluacion.data, cantidades);
    if (error) { setErrorLocal(error); return; }
    const aportes = evaluacion.data.aportes.filter(a => cantidades[a.aporteId] && cantidades[a.aporteId] !== "0").map(a => ({ aporteId: a.aporteId, cantidad: (cantidades[a.aporteId] ?? "").replace(",", ".") }));
    const body = { validacionId: v.validacionId, revision: v.revision, aportes };
    const uuid = identidad(body);
    if (uuid) mutation.mutate({ ruta: "adjudicaciones", body: { ...body, adjudicacionId: uuid } });
  }

  function decidir(accion: string): void {
    if (!v || motivo.trim().length < 3) { setErrorLocal("Explicá el motivo de la decisión."); return; }
    const body = { accion, motivo, validacionId: v.validacionId, revision: v.revision, convocatoriaId: v.convocatoriaId };
    const uuid = identidad(body);
    if (uuid) mutation.mutate({ ruta: "decision-evaluacion", body: { ...body, decisionId: uuid } });
  }

  function recuperar(operacionId: string, accion: string): void {
    const uuid = identidad({ operacionId, accion });
    if (uuid) mutation.mutate({ ruta: `operaciones-nacionales/${operacionId}/recuperacion`, body: { recuperacionId: uuid, accion } });
  }

  const error = mutation.error ?? seguimiento.error ?? evaluacion.error ?? comandos.error;
  return <main className="mx-auto max-w-6xl space-y-6 p-6">
    <Link to="/" className="action-button">Volver al inicio</Link>
    <h1 className="text-2xl font-bold">Evaluación y ejecución de emergencia #{id}</h1>
    <button className="action-button" onClick={() => void queryClient.invalidateQueries({ queryKey: ["ejecucion", id] })}>Actualizar seguimiento</button>
    {(seguimiento.isPending || (!esOng && evaluacion.isPending)) && <p role="status">Cargando evaluación…</p>}
    {(error || errorLocal) && <p role="alert" className="rounded-xl bg-red-50 p-4 text-red-800">{errorLocal ?? (error instanceof ApiError ? error.message : "No pudimos completar la operación. Reintentá.")}</p>}
    {mensaje && <p role="status" className="rounded-xl bg-cyan-50 p-4">{mensaje}</p>}
    {!esOng && evaluacion.isSuccess && !v && <p>La validación nacional todavía no fue confirmada. Esperá el resultado del proceso.</p>}
    {v && <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
      <h2 className="text-xl font-bold">Cobertura compatible</h2>
      <p>{v.lotesCompatiblesCubiertos ? "Todos los lotes tienen cobertura compatible." : "Hay necesidades pendientes de cobertura."} Esta disponibilidad se vuelve a verificar al comprometer.</p>
      {v.cobertura.map(l => <p key={l.loteId}>Lote {l.loteId}: {l.cantidadAsignable} de {l.cantidadRequerida} {l.unidad}; faltante {l.faltante}.</p>)}
      {esMunicipio && v.vigente && !bloqueada && <form onSubmit={e => { e.preventDefault(); seleccionar(); }} className="space-y-4">
        <h3 className="font-bold">Seleccionar aportes</h3>
        {!evaluacion.data?.aportes.length && <p>No hay aportes compatibles para seleccionar.</p>}
        {evaluacion.data?.aportes.map(a => <label key={a.aporteId} className="block rounded-xl border border-slate-200 p-3">
          {a.descripcion || `Oferta ${a.ofertaId}`} · {a.nombreOng || `ONG ${a.ongId}`} · {a.tipoNecesidad || `Lote ${a.loteId}`} · ofrecido {a.cantidadOfrecida}, disponible {a.cantidadDisponible} {a.unidad}
          <input aria-label={`Cantidad aporte ${a.aporteId}`} inputMode="decimal" className="ml-3 w-32 rounded border p-2" value={cantidades[a.aporteId] ?? ""} onChange={e => setCantidades({ ...cantidades, [a.aporteId]: e.target.value })} />
        </label>)}
        {!v.lotesCompatiblesCubiertos && !evaluacion.data?.permiteParcial && <p>El coordinador debe autorizar continuar con cobertura parcial.</p>}
        <button className="action-button action-primary" disabled={mutation.isPending || !evaluacion.data?.aportes.length || (!v.lotesCompatiblesCubiertos && !evaluacion.data?.permiteParcial)}>Solicitar adjudicación</button>
      </form>}
      {rol === "COORDINADOR_REGIONAL" && !v.lotesCompatiblesCubiertos && v.vigente && !bloqueada && <div className="space-y-3">
        <label className="block">Motivo de la decisión<textarea className="block w-full rounded border p-2" value={motivo} onChange={e => setMotivo(e.target.value)} maxLength={1000} /></label>
        {([["REABRIR", "Reabrir convocatoria"], ["REFORMULAR", "Reformular lotes"], ["CONTINUAR_PARCIAL", "Continuar con cobertura parcial"]] as const).map(([accion, texto]) => <button key={accion} className="action-button mr-2" disabled={mutation.isPending} onClick={() => decidir(accion)}>{texto}</button>)}
      </div>}
      {evaluacion.data?.diagnosticos.map((d, i) => <article key={i} className="rounded-xl border border-slate-200 p-4"><h3 className="font-semibold">Oferta {d.ofertaId} · ONG {d.ongId}</h3><ResumenCompetencia perfil={d.perfilCompetencia} /><p>{d.motivos.map(m => m.mensaje).join("; ")}</p></article>)}
    </section>}
    {seguimiento.data && <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
      <h2 className="text-xl font-bold">Seguimiento · {seguimiento.data.estado.replaceAll("_", " ")}</h2>
      {!seguimiento.data.adjudicaciones.length && <p>Todavía no hay una selección enviada.</p>}
      {seguimiento.data.adjudicaciones.map(a => <div key={a.adjudicacionId} className="space-y-3">
        <p>Adjudicación: {a.estado.replaceAll("_", " ")} · integración: {a.estadoIntegracion.replaceAll("_", " ")}</p>
        {a.estado !== "CONFIRMADA" && <p>La ejecución se habilita después de confirmar el compromiso nacional.</p>}
        {a.participantes.map(p => <div key={p.participacionId} className="rounded-xl bg-slate-50 p-3">
          <p>ONG {p.ongId}: {p.estado === "FINALIZACION_SOLICITADA" ? "Finalización informada; liberación pendiente" : p.estado === "LIBERADA" ? "Recursos liberados" : "En ejecución"}</p>
          {esOng && p.estado === "EN_EJECUCION" && <button className="action-button" disabled={mutation.isPending} onClick={() => mutation.mutate({ ruta: `participaciones/${p.participacionId}/finalizacion` })}>Informar finalización</button>}
        </div>)}
      </div>)}
      {rol === "COORDINADOR_REGIONAL" && <button className="action-button action-primary" disabled={mutation.isPending || !seguimiento.data.puedeSolicitarCierre || seguimiento.data.cierre !== null} onClick={() => mutation.mutate({ ruta: "solicitudes-cierre" })}>Solicitar cierre de emergencia</button>}
      {rol === "COORDINADOR_REGIONAL" && seguimiento.data.operaciones.filter(op => !["PENDIENTE", "CONFIRMADA"].includes(op.estadoIntegracion) || op.etapaPendiente).map(op => <div key={op.operacionId} className="space-y-2 rounded-xl bg-amber-50 p-3"><p>{op.tipo}: {op.estadoIntegracion.replaceAll("_", " ")}{op.etapaPendiente ? ` · ${op.etapaPendiente.replaceAll("_", " ")}` : ""}</p>{op.estadoIntegracion !== "RECHAZO_DEFINITIVO" && <button className="action-button" disabled={mutation.isPending} onClick={() => recuperar(op.operacionId, "REINTENTAR_MISMA_OPERACION")}>Recuperar la misma operación</button>}{op.tipo === "COMPROMISO" && op.estadoIntegracion === "RECHAZO_DEFINITIVO" && <button className="action-button" disabled={mutation.isPending} onClick={() => recuperar(op.operacionId, "VOLVER_A_SELECCION")}>Volver a selección municipal</button>}</div>)}
      {seguimiento.data.cierre && <p>Cierre solicitado. La resolución espera la confirmación nacional.</p>}
    </section>}
    {!!comandos.data?.length && <section className="space-y-3"><h2 className="text-xl font-bold">Solicitudes y sincronización</h2>
      {comandos.data.map(c => <div key={c.comandoId} className="rounded-xl border border-slate-200 p-4"><p>{c.estado.replaceAll("_", " ")}</p>{c.error && <p>{c.error}</p>}{c.estado !== "COMPLETADA" && <button className="action-button" disabled={mutation.isPending || c.estado === "EN_PROGRESO"} onClick={() => mutation.mutate({ ruta: `comandos-bonita/${c.comandoId}/reintentar` })}>Reintentar sincronización</button>}</div>)}
    </section>}
  </main>;
}
