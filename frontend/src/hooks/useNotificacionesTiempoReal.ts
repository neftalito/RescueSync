import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { notificacionesWebSocketUrl } from "../api/client";
import { convocatoriasAbiertasQueryKey } from "./useConvocatoriasAbiertas";
import { emergenciasQueryKey } from "./useEmergencias";
import { misOfertasQueryKey } from "./useMisOfertas";
import { notificacionesQueryKey } from "./useNotificaciones";
import {
  eventoNotificacionSchema,
  eventoMetricasSchema,
  type Notificacion,
  type TipoNotificacion,
} from "../schemas/notificacion";

const DEMORA_MAXIMA_RECONEXION_MS = 30_000;

function clavesAInvalidar(
  tipo: TipoNotificacion,
): readonly (readonly string[])[] {
  switch (tipo) {
    case "EMERGENCIA_REGISTRADA":
    case "EMERGENCIA_ESTADO_ACTUALIZADO":
      return [emergenciasQueryKey];
    case "CONVOCATORIA_PUBLICADA":
    case "CONVOCATORIA_ACTUALIZADA":
      return [convocatoriasAbiertasQueryKey];
    case "CONVOCATORIA_CERRADA":
      return [convocatoriasAbiertasQueryKey, misOfertasQueryKey];
    case "OFERTA_RECIBIDA":
      return [];
    case "TAREA_BONITA_FALLIDA":
      return [["metricas"]];
  }
}

export function useNotificacionesTiempoReal(habilitado: boolean): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!habilitado || typeof WebSocket === "undefined") return;

    let socket: WebSocket | null = null;
    let reconexionId: number | null = null;
    let finalizado = false;
    let intentos = 0;

    const conectar = (): void => {
      socket = new WebSocket(notificacionesWebSocketUrl());
      socket.onopen = () => {
        intentos = 0;
        void queryClient.invalidateQueries({
          queryKey: notificacionesQueryKey,
        });
        void queryClient.invalidateQueries({ queryKey: emergenciasQueryKey });
        void queryClient.invalidateQueries({
          queryKey: convocatoriasAbiertasQueryKey,
        });
        void queryClient.invalidateQueries({ queryKey: misOfertasQueryKey });
        void queryClient.invalidateQueries({ queryKey: ["metricas"] });
      };
      socket.onmessage = (mensaje: MessageEvent<unknown>) => {
        let externo: unknown;
        try {
          externo = JSON.parse(String(mensaje.data));
        } catch {
          return;
        }
        if (eventoMetricasSchema.safeParse(externo).success) {
          void queryClient.invalidateQueries({ queryKey: ["metricas"] });
          void queryClient.invalidateQueries({
            queryKey: notificacionesQueryKey,
          });
          return;
        }
        const resultado = eventoNotificacionSchema.safeParse(externo);
        if (!resultado.success) return;

        const nueva = resultado.data.notificacion;
        queryClient.setQueryData<Notificacion[]>(
          notificacionesQueryKey,
          (anteriores = []) => [
            nueva,
            ...anteriores.filter(
              (notificacion) => notificacion.id !== nueva.id,
            ),
          ],
        );
        void queryClient.invalidateQueries({
          queryKey: notificacionesQueryKey,
        });
        for (const queryKey of clavesAInvalidar(nueva.tipo)) {
          void queryClient.invalidateQueries({ queryKey });
        }
      };
      socket.onclose = (evento: CloseEvent) => {
        if (finalizado || evento.code === 1008) return;
        const demora = Math.min(
          1_000 * 2 ** intentos,
          DEMORA_MAXIMA_RECONEXION_MS,
        );
        intentos += 1;
        reconexionId = window.setTimeout(conectar, demora);
      };
    };

    conectar();
    return () => {
      finalizado = true;
      if (reconexionId !== null) window.clearTimeout(reconexionId);
      socket?.close(1000, "Navegación o cierre de sesión");
    };
  }, [habilitado, queryClient]);
}
