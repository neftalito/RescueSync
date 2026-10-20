import { estadoLabels, gravedadLabels } from "../schemas/emergencia";

export const coloresMetricas: Record<string, string> = {
  BAJA: "#15803d",
  MEDIA: "#ca8a04",
  ALTA: "#ea580c",
  CRITICA: "#b91c1c",
  REGISTRADA: "#64748b",
  EN_COORDINACION: "#2563eb",
  PUBLICADA: "#0891b2",
  EN_EVALUACION: "#a16207",
  EN_EJECUCION: "#7c3aed",
  RESUELTA: "#15803d",
  CANCELADA: "#b91c1c",
  INDIVIDUAL: "#0e7490",
  CONJUNTA: "#7c3aed",
};
export const etiquetasMetricas: Record<string, string> = {
  ...estadoLabels,
  ...gravedadLabels,
  INDIVIDUAL: "Individuales",
  CONJUNTA: "Conjuntas confirmadas",
};
