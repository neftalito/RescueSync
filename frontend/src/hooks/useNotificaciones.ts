import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { listarNotificaciones } from "../api/notificaciones";
import type { Notificacion } from "../schemas/notificacion";

export const notificacionesQueryKey = ["notificaciones"] as const;

export function useNotificaciones(): UseQueryResult<Notificacion[], Error> {
  return useQuery({
    queryKey: notificacionesQueryKey,
    queryFn: listarNotificaciones,
    retry: false,
    staleTime: 30_000,
  });
}
