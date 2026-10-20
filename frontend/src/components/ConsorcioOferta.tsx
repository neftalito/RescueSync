import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type ReactElement } from "react";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { ApiError, apiRequest } from "../api/client";
import { misOfertasQueryKey } from "../hooks/useMisOfertas";
import { useSession } from "../hooks/useSession";
import {
  invitacionConsorcioFormSchema,
  maxInvitadasConsorcio,
  ofertaCreadaSchema,
  type InvitacionConsorcioForm,
  type Oferta,
} from "../schemas/oferta";
import { motivoOfertaNoEditable } from "../utils/ofertas";

type AccionConsorcio =
  | { tipo: "proponer"; ongIds: number[] }
  | { tipo: "confirmar" | "desarmar" };

export function ConsorcioOferta({ oferta }: { oferta: Oferta }): ReactElement {
  const session = useSession();
  const client = useQueryClient();
  const id = useId();
  const [mostrando, setMostrando] = useState(false);
  const { register, control, handleSubmit, formState: { errors } } = useForm<InvitacionConsorcioForm>({
    resolver: zodResolver(invitacionConsorcioFormSchema),
    defaultValues: { ongIds: [] },
  });
  const seleccionadas = useWatch({ control, name: "ongIds" });
  const participantes = oferta.participantes ?? [];
  const ongId = session.data?.usuario.organizacion?.id;
  const propio = participantes.find((p) => p.ong_id === ongId);
  const conjunta = participantes.length > 1;
  const motivoSesion = !session.data
    ? session.isError ? "No pudimos verificar tu sesión. Recargá la página." : "Verificando tu sesión…"
    : undefined;
  const motivoInvitacion = !oferta.requiere_desglose_nacional
    ? "Para formar un consorcio, la oferta debe incluir recursos del inventario nacional desglosados por lote."
    : motivoOfertaNoEditable(oferta) ?? motivoSesion;
  const motivoConsorcio = !oferta.consorcio_editable || !["BORRADOR", "PRESENTADA"].includes(oferta.estado)
    ? motivoOfertaNoEditable(oferta) ?? "La convocatoria debe estar abierta y dentro del plazo permitido para modificar el consorcio."
    : motivoSesion ?? (!propio ? "Solo una ONG participante puede modificar el consorcio." : undefined);
  const motivoConfirmacion = motivoConsorcio ?? (propio?.confirmada
    ? "Tu ONG ya confirmó sus aportes a esta versión."
    : oferta.estado !== "BORRADOR" ? "La propuesta ya no está pendiente de confirmación." : undefined);
  const candidatas = useQuery({
    queryKey: ["ongs-consorcio", oferta.convocatoria_id],
    queryFn: () => apiRequest(
      `/ofertas/ongs-disponibles?convocatoria_id=${oferta.convocatoria_id}`,
      z.array(z.object({ ong_id: z.number().int().positive(), nombre: z.string() })),
    ),
    enabled: mostrando && !conjunta && !motivoInvitacion,
    retry: false,
  });
  const accion = useMutation({
    mutationFn: (datos: AccionConsorcio) => apiRequest(
      `/ofertas/${oferta.id}/consorcio${datos.tipo === "confirmar" ? "/confirmacion" : ""}`,
      ofertaCreadaSchema,
      {
        method: datos.tipo === "desarmar" ? "DELETE" : "POST",
        headers: { "X-CSRF-Token": session.data?.csrf_token ?? "" },
        body: JSON.stringify({
          version_bloqueo: oferta.version_bloqueo,
          ...(datos.tipo === "proponer" ? { ong_ids: datos.ongIds } : {}),
        }),
      },
    ),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: misOfertasQueryKey });
      await client.invalidateQueries({ queryKey: ["ongs-consorcio"] });
    },
  });

  return (
    <section className="mt-4 rounded-xl border border-cyan-200 bg-cyan-50 p-4" aria-labelledby={`${id}-titulo`}>
      <h3 id={`${id}-titulo`} className="font-semibold">Oferta conjunta</h3>
      <p className="mt-1 text-sm">Cada ONG presenta sus recursos y confirma la versión conjunta. Si una oferta individual cambia, la propuesta debe renovarse.</p>
      {conjunta ? <>
        <ul className="mt-2">
          {participantes.map((p) => <li key={p.ong_id}>
            {p.nombre} · {p.rol === "LIDER" ? "Líder" : "Integrante"} · {p.confirmada ? "Confirmada" : "Confirmación pendiente"}
          </li>)}
        </ul>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={Boolean(motivoConfirmacion) || accion.isPending}
            aria-describedby={motivoConfirmacion ? `${id}-${motivoConfirmacion === motivoConsorcio ? "consorcio" : "confirmacion"}` : undefined}
            onClick={() => accion.mutate({ tipo: "confirmar" })}
            className="action-button action-primary"
          >Confirmar mis aportes al consorcio</button>
          <button
            type="button"
            disabled={Boolean(motivoConsorcio) || accion.isPending}
            aria-describedby={motivoConsorcio ? `${id}-consorcio` : undefined}
            onClick={() => accion.mutate({ tipo: "desarmar" })}
            className="action-button"
          >Rechazar o desarmar consorcio</button>
        </div>
        {motivoConfirmacion && motivoConfirmacion !== motivoConsorcio && <p id={`${id}-confirmacion`} className="mt-2 text-sm">{motivoConfirmacion}</p>}
        {motivoConsorcio && <p id={`${id}-consorcio`} className="mt-2 text-sm">{motivoConsorcio}</p>}
      </> : <>
        <button
          type="button"
          disabled={Boolean(motivoInvitacion) || accion.isPending}
          aria-describedby={motivoInvitacion ? `${id}-invitacion` : undefined}
          aria-expanded={mostrando}
          onClick={() => setMostrando(true)}
          className="action-button action-primary mt-3"
        >Invitar ONGs</button>
        {motivoInvitacion && <p id={`${id}-invitacion`} className="mt-2 text-sm">{motivoInvitacion}</p>}
        {mostrando && <form
          className="mt-3"
          onSubmit={handleSubmit(({ ongIds }) => accion.mutate({ tipo: "proponer", ongIds: ongIds.map(Number) }))}
        >
          {candidatas.isPending && <p role="status">Cargando ONGs disponibles…</p>}
          {candidatas.isError && <div role="alert">
            <p>No pudimos consultar las ONGs disponibles.</p>
            <button type="button" onClick={() => void candidatas.refetch()} className="action-button mt-2">Reintentar consulta de ONGs</button>
          </div>}
          {candidatas.data && <fieldset disabled={Boolean(motivoInvitacion) || accion.isPending}>
            <legend className="font-semibold">ONGs participantes</legend>
            <p id={`${id}-limite`} className="mt-1 text-sm">Seleccioná hasta {maxInvitadasConsorcio} ONGs para invitar, además de tu ONG líder. Cada una debe tener una oferta individual en esta convocatoria.</p>
            <div className="mt-2 max-h-64 space-y-1 overflow-y-auto">
              {candidatas.data.map((ong) => <label key={ong.ong_id} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg px-2 py-2 hover:bg-cyan-100">
                <input
                  type="checkbox"
                  value={String(ong.ong_id)}
                  {...register("ongIds")}
                  disabled={seleccionadas.length >= maxInvitadasConsorcio && !seleccionadas.includes(String(ong.ong_id))}
                  aria-describedby={`${id}-limite`}
                  className="size-4 shrink-0 accent-cyan-700 disabled:cursor-not-allowed"
                />
                <span>{ong.nombre}</span>
              </label>)}
            </div>
            <p className="mt-2 text-sm" aria-live="polite">{seleccionadas.length} de {maxInvitadasConsorcio} ONGs seleccionadas.</p>
          </fieldset>}
          {candidatas.data?.length === 0 && <p className="mt-2">No hay otras ofertas individuales con recursos nacionales en esta convocatoria.</p>}
          {errors.ongIds && <p role="alert">{errors.ongIds.message}</p>}
          <button
            type="submit"
            disabled={seleccionadas.length === 0 || Boolean(motivoInvitacion) || accion.isPending || candidatas.isFetching || candidatas.isError}
            className="action-button action-primary mt-3"
          >Enviar propuesta de consorcio</button>
        </form>}
      </>}
      {accion.isPending && <p role="status">Guardando propuesta…</p>}
      {accion.isError && <p role="alert">{accion.error instanceof ApiError ? accion.error.message : "No pudimos guardar la propuesta."}</p>}
      {accion.isSuccess && <p role="status">Propuesta actualizada.</p>}
    </section>
  );
}
