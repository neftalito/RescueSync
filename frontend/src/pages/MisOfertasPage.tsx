import { useId, useState, type ReactElement } from "react";
import { Link } from "react-router";

import { ListadoRemoto } from "../components/ListadoProgresivo";
import { ActionIcon } from "../components/ActionIcon";
import { CampoBusqueda } from "../components/CampoBusqueda";
import { SelectorFiltro } from "../components/SelectorFiltro";
import { ApiError } from "../api/client";
import { ConsorcioOferta } from "../components/ConsorcioOferta";
import { useMisOfertasPaginadas } from "../hooks/useMisOfertas";
import { useTextoBusqueda } from "../hooks/useTextoBusqueda";
import { gravedadLabels } from "../schemas/emergencia";
import { estadoOfertaLabels, estadosOferta, tipoAporteLabels, type Oferta } from "../schemas/oferta";
import { formatearCantidad } from "../utils/cantidades";
import { motivoOfertaNoEditable } from "../utils/ofertas";

function formatearFecha(iso: string): string {
  return new Date(iso).toLocaleString("es-AR", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function TarjetaOferta({ oferta }: { oferta: Oferta; }): ReactElement {
  const motivoEdicionId = useId();
  const motivoEdicion = motivoOfertaNoEditable(oferta);
  return (
    <details className="group rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4">
        <div>
          <p className="text-sm font-semibold text-cyan-800">
            {gravedadLabels[oferta.emergencia.gravedad]} · {oferta.emergencia.zona}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {oferta.presentada_en ? `Presentada el ${formatearFecha(oferta.presentada_en)}` : "Propuesta pendiente de confirmación"}
          </p>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
          {estadoOfertaLabels[oferta.estado]}
        </span>
      </summary>
      <div className="mt-4 space-y-2 border-t border-slate-100 pt-4 text-sm leading-6 text-slate-600">
        <p>{oferta.emergencia.descripcion}</p>
        {oferta.observaciones && <p>{oferta.observaciones}</p>}
        <ul className="space-y-1">
          {oferta.items.map((item) => (
            <li key={item.id}>
              {item.descripcion} — {formatearCantidad(item.cantidad_ofrecida)}{" "}
              {item.unidad} ({tipoAporteLabels[item.tipo]})
            </li>
          ))}
        </ul>
        {oferta.estado === "ADJUDICADA" && <Link to={`/emergencias/${oferta.emergencia_id}/ejecucion`} className="action-button">Seguimiento y finalización</Link>}
        {oferta.editable ? (
          <Link
            to={`/ofertas/${oferta.id}/editar`}
            className="action-button action-primary action-icon mt-4"
            title="Modificar oferta"
          >
            <ActionIcon name="edit" />
            <span className="sr-only">Modificar oferta</span>
          </Link>
        ) : (
          <div className="mt-4">
            <button
              type="button"
              disabled
              className="action-button action-primary action-icon"
              title="Modificar oferta"
              aria-describedby={motivoEdicionId}
            >
              <ActionIcon name="edit" />
              <span className="sr-only">Modificar oferta</span>
            </button>
            <p id={motivoEdicionId} className="mt-2 text-sm">{motivoEdicion}</p>
          </div>
        )}
        <ConsorcioOferta oferta={oferta} />
      </div>
    </details>
  );
}

export function MisOfertasPage(): ReactElement {
  const busqueda = useTextoBusqueda();
  const [estado, setEstado] = useState("");
  const query = useMisOfertasPaginadas(busqueda.termino, estadosOferta.find((valor) => valor === estado));

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div>
            <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
              RescueSync
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-950">Mis ofertas</h1>
          </div>
          <Link
            to="/"
            className="action-button action-icon"
            title="Volver al inicio"
          >
            <ActionIcon name="home" />
            <span className="sr-only">Volver al inicio</span>
          </Link>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-6">
        <div className="mb-4 grid gap-4 sm:grid-cols-2">
          <CampoBusqueda etiqueta="Buscar ofertas" ejemplo="Emergencia, aporte u observación" valor={busqueda.texto} cambiar={busqueda.cambiar} />
          <SelectorFiltro etiqueta="Estado de la oferta" valor={estado} cambiar={setEstado}>
            <option value="">Todos los estados</option>
            {estadosOferta.map((valor) => <option key={valor} value={valor}>{estadoOfertaLabels[valor]}</option>)}
          </SelectorFiltro>
        </div>
        {query.isPending ? (
          <section
            role="status"
            className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm"
          >
            Cargando tus ofertas…
          </section>
        ) : query.data === undefined ? (
          <section
            role="alert"
            className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm leading-6 text-red-800 shadow-sm"
          >
            <p>
              {query.error instanceof ApiError
                ? query.error.message
                : "No pudimos consultar tus ofertas. Intentá nuevamente."}
            </p>
            <button
              type="button"
              onClick={() => void query.refetch()}
              className="action-button action-danger action-icon mt-4"
              title="Reintentar"
            >
              <ActionIcon name="refresh" />
              <span className="sr-only">Reintentar</span>
            </button>
          </section>
        ) : query.data.length === 0 ? (
          <p
            role="status"
            className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm"
          >
            {busqueda.termino || estado
              ? "No encontramos ofertas que coincidan con la búsqueda y los filtros."
              : "Todavía no presentaste ofertas."}
          </p>
        ) : (
          <ListadoRemoto query={query} etiqueta="Mis ofertas">
            <div className="space-y-4">
              {query.data.map((oferta) => (
                <TarjetaOferta key={oferta.id} oferta={oferta} />
              ))}
            </div>
          </ListadoRemoto>
        )}
      </div>
    </main>
  );
}
