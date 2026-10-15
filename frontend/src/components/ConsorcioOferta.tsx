import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactElement } from "react";
import { z } from "zod";
import { ApiError, apiRequest } from "../api/client";
import { useSession } from "../hooks/useSession";
import { misOfertasQueryKey } from "../hooks/useMisOfertas";
import { ofertaCreadaSchema, type Oferta } from "../schemas/oferta";
export function ConsorcioOferta({ oferta }: {
    oferta: Oferta;
}): ReactElement {
    const session = useSession();
    const client = useQueryClient();
    const [seleccionada, setSeleccionada] = useState("");
    const participantes = oferta.participantes ?? [];
    const ongId = session.data?.usuario.organizacion?.id;
    const propio = participantes.find((p) => p.ong_id === ongId);
    const conjunta = participantes.length > 1;
    const [mostrando, setMostrando] = useState(false);
    const candidatas = useQuery({
        queryKey: ["ongs-consorcio", oferta.convocatoria_id],
        queryFn: () => apiRequest(`/ofertas/ongs-disponibles?convocatoria_id=${oferta.convocatoria_id}`, z.array(z.object({ ong_id: z.number().int(), nombre: z.string() }))),
        enabled: mostrando && !conjunta, retry: false,
    });
    const accion = useMutation({
        mutationFn: (tipo: "proponer" | "confirmar" | "desarmar") => apiRequest(`/ofertas/${oferta.id}/consorcio${tipo === "confirmar" ? "/confirmacion" : ""}`, ofertaCreadaSchema, { method: tipo === "desarmar" ? "DELETE" : "POST", headers: { "X-CSRF-Token": session.data?.csrf_token ?? "" },
            body: JSON.stringify({ version_bloqueo: oferta.version_bloqueo, ...(tipo === "proponer" ? { ong_ids: [Number(seleccionada)] } : {}) }) }),
        onSuccess: async () => { await client.invalidateQueries({ queryKey: misOfertasQueryKey }); await client.invalidateQueries({ queryKey: ["ongs-consorcio"] }); },
    });
    return <section className="mt-4 rounded-xl border border-cyan-200 bg-cyan-50 p-4">
    <h3 className="font-semibold">Oferta conjunta</h3>
    <p className="mt-1 text-sm">Cada ONG presenta sus recursos y confirma la versión conjunta. Si una oferta individual cambia, la propuesta debe renovarse.</p>
    {conjunta ? <>
      <ul className="mt-2">{participantes.map((p) => <li key={p.ong_id}>{p.nombre} · {p.rol === "LIDER" ? "Líder" : "Integrante"} · {p.confirmada ? "Confirmada" : "Confirmación pendiente"}</li>)}</ul>
      {oferta.consorcio_editable && oferta.estado === "BORRADOR" && propio && !propio.confirmada && <button type="button" disabled={accion.isPending || !session.data} onClick={() => accion.mutate("confirmar")} className="action-button action-primary mt-3">Confirmar mis aportes al consorcio</button>}
      {oferta.consorcio_editable && propio && ["BORRADOR", "PRESENTADA"].includes(oferta.estado) && <button type="button" disabled={accion.isPending || !session.data} onClick={() => accion.mutate("desarmar")} className="action-button ml-2 mt-3">Rechazar o desarmar consorcio</button>}
    </> : oferta.editable ? <>
      <button type="button" className="action-button action-primary mt-3" onClick={() => setMostrando(true)}>Invitar una ONG</button>
      {mostrando && <>
        {candidatas.isPending && <p role="status">Cargando ONGs disponibles…</p>}
        {candidatas.isError && <p role="alert">No pudimos consultar las ONGs disponibles.</p>}
        {candidatas.data && <label className="mt-3 block">ONG participante
          <select value={seleccionada} onChange={(event) => setSeleccionada(event.target.value)} className="ml-2 rounded border border-slate-300 bg-white p-2">
            <option value="">Elegí una ONG</option>
            {candidatas.data.map((o) => <option key={o.ong_id} value={o.ong_id}>{o.nombre}</option>)}
          </select>
        </label>}
        {candidatas.data?.length === 0 && <p>No hay otras ofertas individuales con recursos nacionales en esta convocatoria.</p>}
        <button type="button" disabled={!seleccionada || accion.isPending || !session.data} onClick={() => accion.mutate("proponer")} className="action-button action-primary mt-3">Enviar propuesta de consorcio</button>
      </>}
    </> : <p className="mt-2">La oferta ya no admite nuevas propuestas.</p>}
    {accion.isPending && <p role="status">Guardando propuesta…</p>}
    {accion.isError && <p role="alert">{accion.error instanceof ApiError ? accion.error.message : "No pudimos guardar la propuesta."}</p>}
    {accion.isSuccess && <p role="status">Propuesta actualizada.</p>}
  </section>;
}
