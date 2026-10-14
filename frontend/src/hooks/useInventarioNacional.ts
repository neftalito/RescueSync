import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  actualizarRecurso,
  conectarCuenta,
  consultarCapacidades,
  consultarConexion,
  consultarRecursos,
  crearRecurso,
  desconectarCuenta,
  registrarOngNacional,
} from "../api/inventario";
import { ApiError } from "../api/client";
import {
  consultarCertificaciones,
  consultarCatalogoCertificaciones,
} from "../api/certificaciones";
import type {
  Certificacion,
  CertificacionesOng,
} from "../schemas/certificaciones";
import type { Session } from "../schemas/auth";
import type {
  Capacidad,
  ConexionEstado,
  ConexionForm,
  Recurso,
  RecursoForm,
  OngNacional,
  RegistroNacionalForm,
} from "../schemas/inventario";

interface InventarioNacional {
  conexion: UseQueryResult<ConexionEstado>;
  recursos: UseQueryResult<Recurso[]>;
  capacidades: UseQueryResult<Capacidad[]>;
  certificaciones: UseQueryResult<CertificacionesOng>;
  catalogoCertificaciones: UseQueryResult<Certificacion[]>;
  conectar: UseMutationResult<ConexionEstado, Error, ConexionForm>;
  registrar: UseMutationResult<OngNacional, Error, RegistroNacionalForm>;
  desconectar: UseMutationResult<void, Error, void>;
  crear: UseMutationResult<Recurso, Error, RecursoForm>;
  editar: UseMutationResult<
    Recurso,
    Error,
    { recurso: Recurso; cantidadTotal: string }
  >;
  actualizar: () => Promise<void>;
}

export function useInventarioNacional(session: Session): InventarioNacional {
  const client = useQueryClient();
  const key = ["inventario", session.usuario.id] as const;
  const limpiarCertificaciones = (): void => {
    client.removeQueries({ queryKey: [...key, "certificaciones"] });
    client.removeQueries({ queryKey: [...key, "catalogo-certificaciones"] });
  };
  const consultar = async <T>(operacion: () => Promise<T>): Promise<T> => {
    try {
      return await operacion();
    } catch (error: unknown) {
      if (error instanceof ApiError && [401, 403].includes(error.status)) {
        limpiarCertificaciones();
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
    queryKey: [...key, "recursos"],
    queryFn: () => consultar(consultarRecursos),
    enabled: conexion.data?.conectada === true,
    retry: false,
  });
  const capacidades = useQuery({
    queryKey: [...key, "capacidades"],
    queryFn: () => consultar(consultarCapacidades),
    enabled: conexion.data?.conectada === true,
    retry: false,
  });
  const certificaciones = useQuery({
    queryKey: [...key, "certificaciones", conexion.data?.ongId],
    queryFn: () => consultar(consultarCertificaciones),
    enabled: conexion.data?.conectada === true,
    retry: false,
    refetchInterval: 60_000,
  });
  const catalogoCertificaciones = useQuery({
    queryKey: [...key, "catalogo-certificaciones", conexion.data?.ongId],
    queryFn: () => consultar(consultarCatalogoCertificaciones),
    enabled: conexion.data?.conectada === true,
    retry: false,
  });
  const actualizar = async (): Promise<void> => {
    await client.invalidateQueries({ queryKey: key });
  };
  const fallo = async (error: Error): Promise<void> => {
    if (error instanceof ApiError && [401, 403].includes(error.status)) {
      client.removeQueries({ queryKey: [...key, "recursos"] });
      client.removeQueries({ queryKey: [...key, "capacidades"] });
      limpiarCertificaciones();
      await client.invalidateQueries({ queryKey: [...key, "conexion"] });
    } else {
      await client.invalidateQueries({ queryKey: [...key, "recursos"] });
    }
  };
  const conectar = useMutation({
    mutationFn: (datos: ConexionForm) =>
      conectarCuenta(datos, session.csrf_token),
    onSuccess: actualizar,
    onSettled: (_data, _error, datos) => {
      datos.password = "";
    },
  });
  const registrar = useMutation({
    mutationFn: (datos: RegistroNacionalForm) =>
      registrarOngNacional(datos, session.csrf_token),
    retry: false,
    onSettled: (_data, _error, datos) => {
      datos.password = "";
    },
  });
  const desconectar = useMutation({
    mutationFn: () => desconectarCuenta(session.csrf_token),
    onSuccess: async () => {
      client.removeQueries({ queryKey: [...key, "recursos"] });
      client.removeQueries({ queryKey: [...key, "capacidades"] });
      limpiarCertificaciones();
      await actualizar();
    },
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
    certificaciones,
    catalogoCertificaciones,
    conectar,
    registrar,
    desconectar,
    crear,
    editar,
    actualizar,
  };
}
