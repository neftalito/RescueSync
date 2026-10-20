import type { Role } from "../../schemas/auth";
import type { DetalleNotificacion, OfertaNotificada } from "../../schemas/detalleNotificacion";
import type { TipoNotificacion } from "../../schemas/notificacion";

const emergencia = {
  id: 20, zona: "Ribera norte", descripcion: "Inundación con familias evacuadas",
  gravedad: "ALTA" as const, estado: "EN_EVALUACION" as const,
};
const oferta: OfertaNotificada = {
  id: 12, estado: "PRESENTADA", version: 1,
  presentada_en: "2026-10-19T10:00:00Z", observaciones: "Disponibilidad inmediata",
  participantes: [{ ong_id: 3, nombre: "Ayuda del Delta", rol: "LIDER", confirmada: true }],
  items: [{ id: 4, lote_id: 8, necesidad: "Agua potable", tipo: "RECURSO",
    descripcion: "Bidones de agua", cantidad_ofrecida: "25.000", unidad: "litros", aportes: [] }],
};
const convocatoria = {
  id: 11, emergencia_id: 20, numero: 1,
  publicada_en: "2026-10-18T10:00:00Z", cierra_en: "2026-10-19T10:00:00Z",
  emergencia,
  lotes: [{ lote_id: 8, tipo_necesidad: "Agua potable", descripcion: "Para familias evacuadas",
    cantidad_publicada: "100.000", unidad_publicada: "litros" }],
};

interface CasoDetalle {
  nombre: string;
  rol: Role;
  tipo: TipoNotificacion;
  titulo: string;
  id: number;
  detalle: DetalleNotificacion;
}

export const casosDetalle: CasoDetalle[] = [
  {
    nombre: "oferta recibida", rol: "COORDINADOR_REGIONAL", tipo: "OFERTA_RECIBIDA",
    titulo: "Nueva oferta recibida", id: 41,
    detalle: { clase: "OFERTA_RECIBIDA", emergencia, oferta, convocatoria_numero: 1 },
  },
  {
    nombre: "tarea fallida", rol: "AUDITOR_DIRECTIVO", tipo: "TAREA_BONITA_FALLIDA",
    titulo: "Tarea de Bonita con errores", id: 42,
    detalle: { clase: "TAREA_BONITA_FALLIDA", emergencia, tarea_id: 99,
      nombre: "Validar ofertas", estado_observado: "failed", observada_en: "2026-10-19T10:00:00Z" },
  },
  {
    nombre: "convocatoria abierta", rol: "REPRESENTANTE_ONG", tipo: "CONVOCATORIA_PUBLICADA",
    titulo: "Nueva convocatoria abierta", id: 43,
    detalle: { clase: "CONVOCATORIA", emergencia,
      convocatoria: { ...convocatoria, estado: "ABIERTA" }, mi_oferta: null },
  },
  {
    nombre: "convocatoria cerrada con oferta propia", rol: "REPRESENTANTE_ONG", tipo: "CONVOCATORIA_CERRADA",
    titulo: "Convocatoria cerrada", id: 44,
    detalle: { clase: "CONVOCATORIA", emergencia,
      convocatoria: { ...convocatoria, estado: "CERRADA" }, mi_oferta: oferta },
  },
  {
    nombre: "convocatoria cerrada sin participación", rol: "REPRESENTANTE_ONG", tipo: "CONVOCATORIA_CERRADA",
    titulo: "Convocatoria cerrada", id: 45,
    detalle: { clase: "CONVOCATORIA", emergencia,
      convocatoria: { ...convocatoria, estado: "CERRADA" }, mi_oferta: null },
  },
];
