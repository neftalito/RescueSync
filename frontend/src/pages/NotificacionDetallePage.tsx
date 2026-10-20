import { useQuery } from "@tanstack/react-query";
import { type ReactElement } from "react";
import { Link, useParams } from "react-router";

import { apiRequest, ApiError } from "../api/client";
import { detalleNotificacionSchema, type DetalleNotificacion, type OfertaNotificada } from "../schemas/detalleNotificacion";
import { estadoConvocatoriaLabels } from "../schemas/convocatoria";
import { estadoLabels, gravedadLabels } from "../schemas/emergencia";
import { estadoOfertaLabels, tipoAporteLabels } from "../schemas/oferta";
import { formatearCantidad } from "../utils/cantidades";

function fecha(valor: string): string {
  return new Date(valor).toLocaleString("es-AR", { dateStyle: "medium", timeStyle: "short" });
}

function OfertaDetalle({ oferta }: { oferta: OfertaNotificada }): ReactElement {
  return <section aria-label="Detalle de la oferta" className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5">
    <h2 className="text-xl font-semibold">Oferta #{oferta.id}</h2>
    <p>Estado actual: {estadoOfertaLabels[oferta.estado]}</p>
    <p>{oferta.presentada_en
      ? `Última versión presentada: ${oferta.version} · ${fecha(oferta.presentada_en)}`
      : "Propuesta pendiente de confirmación. Sus aportes aún no fueron presentados."}</p>
    <h3 className="font-semibold">ONGs participantes</h3>
    <ul className="list-inside list-disc">{oferta.participantes.map(p => <li key={p.ong_id}>{p.nombre} · {p.rol === "LIDER" ? "Líder" : "Miembro"}</li>)}</ul>
    {oferta.observaciones && <p className="whitespace-pre-wrap break-words">{oferta.observaciones}</p>}
    <h3 className="font-semibold">Aportes presentados</h3>
    {oferta.items.length === 0 ? <p>No hay aportes presentados en esta versión.</p> : <ul className="space-y-3">
      {oferta.items.map(item => <li key={item.id} className="rounded-xl bg-slate-50 p-4">
        <p className="font-semibold">{item.necesidad}</p>
        <p>{tipoAporteLabels[item.tipo]} · {formatearCantidad(item.cantidad_ofrecida)} {item.unidad}</p>
        <p className="whitespace-pre-wrap break-words">{item.descripcion}</p>
        {item.aportes && item.aportes.length > 0 && <ul className="mt-2 space-y-1">{item.aportes.map(aporte => <li key={aporte.id}>
          {oferta.participantes.find(p => p.ong_id === aporte.ong_id)?.nombre ?? "ONG participante"}: {formatearCantidad(aporte.cantidad)} {aporte.unidad}
        </li>)}</ul>}
      </li>)}
    </ul>}
  </section>;
}

function Contenido({ detalle }: { detalle: DetalleNotificacion }): ReactElement {
  const emergencia = detalle.emergencia;
  return <div className="space-y-5">
    <section aria-label="Emergencia del aviso" className="space-y-2 rounded-2xl border border-slate-200 bg-white p-5">
      <h2 className="text-xl font-semibold">{emergencia.zona}</h2>
      <p>Emergencia #{emergencia.id} · {gravedadLabels[emergencia.gravedad]} · {estadoLabels[emergencia.estado]}</p>
      <p className="whitespace-pre-wrap break-words">{emergencia.descripcion}</p>
    </section>
    {detalle.clase === "OFERTA_RECIBIDA" && <>
      <p>Oferta recibida para la convocatoria N.º {detalle.convocatoria_numero}.</p>
      <OfertaDetalle oferta={detalle.oferta} />
    </>}
    {detalle.clase === "CONVOCATORIA" && <>
      <section aria-label="Convocatoria del aviso" className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-xl font-semibold">Convocatoria N.º {detalle.convocatoria.numero}</h2>
        <p>Estado actual: {estadoConvocatoriaLabels[detalle.convocatoria.estado]}</p>
        <p>Publicada: {fecha(detalle.convocatoria.publicada_en)}</p>
        <p>Plazo de recepción: {fecha(detalle.convocatoria.cierra_en)}</p>
        <h3 className="font-semibold">Lotes de esta convocatoria</h3>
        <ul className="space-y-3">{detalle.convocatoria.lotes.map(lote => <li key={lote.lote_id} className="rounded-xl bg-slate-50 p-4">
          <p className="font-semibold">{lote.tipo_necesidad}</p>
          <p>{formatearCantidad(lote.cantidad_publicada)} {lote.unidad_publicada}</p>
          {lote.descripcion && <p className="whitespace-pre-wrap break-words">{lote.descripcion}</p>}
        </li>)}</ul>
      </section>
      {detalle.mi_oferta ? <OfertaDetalle oferta={detalle.mi_oferta} /> : <p role="status" className="rounded-xl bg-slate-100 p-4">
        {detalle.convocatoria.estado === "ABIERTA" ? "Tu ONG todavía no presentó una oferta para esta convocatoria." : "Tu ONG no participó en esta convocatoria."}
      </p>}
    </>}
    {detalle.clase === "TAREA_BONITA_FALLIDA" && <section aria-label="Tarea fallida del aviso" className="space-y-3 rounded-2xl border border-slate-200 bg-white p-5">
      <h2 className="text-xl font-semibold">{detalle.nombre}</h2>
      <p>Tarea #{detalle.tarea_id}</p>
      <p>Estado al generar el aviso: Fallida</p>
      <p>Observada: {fecha(detalle.observada_en)}</p>
      <p>Este aviso conserva el incidente observado. El estado de la tarea puede haber cambiado después.</p>
    </section>}
  </div>;
}

export function NotificacionDetallePage(): ReactElement {
  const parametro = useParams().notificacionId ?? "";
  const id = Number(parametro);
  const valido = /^[1-9]\d*$/.test(parametro) && Number.isSafeInteger(id);
  const query = useQuery({
    queryKey: ["notificaciones", "detalle", id],
    queryFn: () => apiRequest(`/notificaciones/${id}/detalle`, detalleNotificacionSchema),
    enabled: valido, retry: false,
  });
  const titulo = query.data?.clase === "OFERTA_RECIBIDA" ? "Detalle de oferta recibida"
    : query.data?.clase === "TAREA_BONITA_FALLIDA" ? "Detalle de tarea fallida"
    : query.data?.clase === "CONVOCATORIA" ? "Detalle de convocatoria" : "Detalle de notificación";
  return <main className="mx-auto max-w-4xl space-y-6 px-4 py-6 [overflow-wrap:anywhere] sm:px-6">
    <Link to="/" className="action-button">Volver al inicio</Link>
    <h1 className="text-2xl font-bold">{titulo}</h1>
    {!valido ? <p role="alert">El identificador de notificación no es válido.</p>
      : query.isPending ? <p role="status">Cargando detalle…</p>
      : query.isError ? <div role="alert" className="space-y-3 rounded-xl bg-red-50 p-4 text-red-800">
        <p>{query.error instanceof ApiError ? query.error.message : "No pudimos cargar el detalle de la notificación."}</p>
        <button type="button" className="action-button" onClick={() => void query.refetch()}>Reintentar</button>
      </div> : query.data && <Contenido detalle={query.data} />}
  </main>;
}
