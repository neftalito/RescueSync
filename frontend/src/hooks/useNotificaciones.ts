import { useQuery, type UseInfiniteQueryResult, type UseQueryResult } from "@tanstack/react-query";

import { listarNotificaciones } from "../api/notificaciones";
import type { Notificacion } from "../schemas/notificacion";
import { notificacionesSchema } from "../schemas/notificacion";
import { useListadoPaginado } from "./useListadoPaginado";

export const notificacionesQueryKey = ["notificaciones"] as const;

export function useNotificacionesPaginadas(habilitado: boolean): UseInfiniteQueryResult<Notificacion[], Error> {
  return useListadoPaginado(notificacionesQueryKey, "/notificaciones", notificacionesSchema, habilitado);
}

export function useNotificaciones(): UseQueryResult<Notificacion[], Error> {
  return useQuery({
    queryKey: notificacionesQueryKey,
    queryFn: listarNotificaciones,
    retry: false,
    staleTime: 30_000,
  });
}
