import type { ReactElement } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import { ApiError } from "../api/client";
import type { PerfilCompetencia } from "../schemas/perfiles";
import { formatearCantidad } from "../utils/cantidades";
import { ListadoLocal } from "./ListadoProgresivo";

export function ResumenCompetencia({ perfil }: { perfil: PerfilCompetencia | null }): ReactElement {
  return <div className="space-y-3">
    <p className="text-sm text-slate-600">Análisis informativo de recursos declarados. La disponibilidad puede cambiar hasta confirmar el compromiso.</p>
    {!perfil ? <p>Perfil informativo no disponible.</p> : <>
      <p className="text-sm text-slate-600">Consultado: {new Date(perfil.evaluadoEn).toLocaleString()}</p>
      {!perfil.capacidadesDeclaradas.length ? <p>No hay recursos activos declarados.</p> :
        <ListadoLocal items={perfil.capacidadesDeclaradas} etiqueta="Capacidades declaradas">
          {(visibles) => <ul className="space-y-3">{visibles.map(c => <li key={c.capacidadId} className="rounded-xl border border-slate-200 p-4">
            <h3 className="font-semibold">{c.nombre}</h3>
            <dl className="mt-2 flex flex-wrap gap-4 text-sm">
              <div><dt>Total</dt><dd>{formatearCantidad(c.cantidadTotal)} {c.unidad}</dd></div>
              <div><dt>Comprometido</dt><dd>{formatearCantidad(c.cantidadComprometida)} {c.unidad}</dd></div>
              <div><dt>Disponible</dt><dd>{formatearCantidad(c.cantidadDisponible)} {c.unidad}</dd></div>
            </dl>
          </li>)}</ul>}
        </ListadoLocal>}
    </>}
  </div>;
}

export function PerfilCompetenciaPanel({ perfil }: { perfil: UseQueryResult<PerfilCompetencia> }): ReactElement {
  return <section aria-labelledby="perfil-competencia" className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 id="perfil-competencia" className="text-xl font-bold">Perfil de competencia</h2>
      <button type="button" className="action-button" disabled={perfil.isFetching} onClick={() => void perfil.refetch()}>Actualizar perfil</button>
    </div>
    {perfil.isPending ? <p role="status">Consultando perfil…</p> : perfil.isError ?
      <p role="alert">{perfil.error instanceof ApiError ? perfil.error.message : "No pudimos consultar el perfil de competencia."}</p> : <>
        <p>{perfil.data.nombre} · {perfil.data.estadoOng === "HABILITADA" ? "Activa" : perfil.data.estadoOng}</p>
        <ResumenCompetencia perfil={perfil.data} />
      </>}
  </section>;
}
