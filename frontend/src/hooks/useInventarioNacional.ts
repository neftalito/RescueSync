import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  actualizarRecurso,
  consultarCapacidades,
  consultarConexion,
  consultarRecursos,
  crearRecurso,
  registrarOngNacional,
} from "../api/inventario";
import { ApiError } from "../api/client";
import { consultarPerfilCompetencia } from "../api/perfiles";
import type { PerfilCompetencia } from "../schemas/perfiles";
import type { Session } from "../schemas/auth";
import type {
  Capacidad,
  ConexionEstado,
  Recurso,
  RecursoForm,
  OngNacional,
  RegistroNacionalForm,
} from "../schemas/inventario";

interface InventarioNacional {
  conexion: UseQueryResult<ConexionEstado>;
  recursos: UseQueryResult<Recurso[]>;
  capacidades: UseQueryResult<Capacidad[]>;
  perfil: UseQueryResult<PerfilCompetencia>;
  registrar: UseMutationResult<OngNacional, Error, RegistroNacionalForm>;
  crear: UseMutationResult<Recurso, Error, RecursoForm>;
  editar: UseMutationResult<
    Recurso,
    Error,
    { recurso: Recurso; cantidadTotal: string }
  >;
  actualizar: () => Promise<void>;
}

export function useInventarioNacional(
  session: Session,
  vista: "inventario" | "perfil",
): InventarioNacional {
  const client = useQueryClient();
  const key = ["inventario", session.usuario.id] as const;
  const limpiarPerfil = (): void => {
    client.removeQueries({ queryKey: [...key, "perfil"] });
  };
  const consultar = async <T>(operacion: () => Promise<T>): Promise<T> => {
    try {
      return await operacion();
    } catch (error: unknown) {
      if (error instanceof ApiError && [401, 403, 503].includes(error.status)) {
        limpiarPerfil();
        client.setQueryData<ConexionEstado>([...key, "conexion"], (actual) =>
          actual ? { ...actual, conectada: false } : actual,
        );
        await client.invalidateQueries({ queryKey: [...key, "conexion"] });
      }
      throw error;
    }
  };
  const conexion = useQuery({
    queryKey: [...key, "conexion"],
    queryFn: consultarConexion,
    retry: false,
    refetchInterval: 60_000,
  });
  const recursos = useQuery({
    queryKey: [...key, "recursos", conexion.data?.ongId],
    queryFn: () => consultar(consultarRecursos),
    enabled: conexion.data?.estado === "LISTA" && vista === "inventario",
    retry: false,
  });
  const capacidades = useQuery({
    queryKey: [...key, "capacidades", conexion.data?.ongId],
    queryFn: () => consultar(consultarCapacidades),
    enabled: conexion.data?.estado === "LISTA" && vista === "inventario",
    retry: false,
  });
  const perfil = useQuery({
    queryKey: [...key, "perfil", conexion.data?.ongId],
    queryFn: () => consultar(consultarPerfilCompetencia),
    enabled: conexion.data?.estado === "LISTA" && vista === "perfil",
    retry: false,
    refetchInterval: 60_000,
  });
  const actualizar = async (): Promise<void> => {
    await client.invalidateQueries({ queryKey: key });
  };
  const fallo = async (error: Error): Promise<void> => {
    if (error instanceof ApiError && [401, 403, 503].includes(error.status)) {
      client.removeQueries({ queryKey: [...key, "recursos"] });
      client.removeQueries({ queryKey: [...key, "capacidades"] });
      limpiarPerfil();
      await client.invalidateQueries({ queryKey: [...key, "conexion"] });
    } else {
      await client.invalidateQueries({ queryKey: [...key, "recursos"] });
    }
  };
  const registrar = useMutation({
    mutationFn: (datos: RegistroNacionalForm) =>
      registrarOngNacional(datos, session.csrf_token),
    retry: false,
    onSuccess: actualizar,
  });
  const crear = useMutation({
    mutationFn: (datos: RecursoForm) => crearRecurso(datos, session.csrf_token),
    onSuccess: actualizar,
    onError: fallo,
  });
  const editar = useMutation({
    mutationFn: ({
      recurso,
      cantidadTotal,
    }: {
      recurso: Recurso;
      cantidadTotal: string;
    }) => actualizarRecurso(recurso, cantidadTotal, session.csrf_token),
    onSuccess: actualizar,
    onError: fallo,
  });
  return {
    conexion,
    recursos,
    capacidades,
    perfil,
    registrar,
    crear,
    editar,
    actualizar,
  };
}
