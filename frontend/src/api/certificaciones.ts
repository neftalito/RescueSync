import { z } from "zod";
import { apiRequest } from "./client";
import {
  certificacionSchema,
  certificacionesOngSchema,
  type Certificacion,
  type CertificacionesOng,
} from "../schemas/certificaciones";

export const consultarCertificaciones = (): Promise<CertificacionesOng> =>
  apiRequest("/mi-ong/certificaciones", certificacionesOngSchema);

export const consultarCatalogoCertificaciones = (): Promise<Certificacion[]> =>
  apiRequest("/mi-ong/catalogo-certificaciones", z.array(certificacionSchema));
