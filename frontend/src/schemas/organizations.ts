import { z } from "zod";

import { organizationSchema } from "./auth";

export const organizationTypes = [
  "MUNICIPIO",
  "CENTRO_COORDINADOR",
  "ONG",
] as const;

export type OrganizationType = (typeof organizationTypes)[number];

export const organizationTypeLabels: Record<OrganizationType, string> = {
  MUNICIPIO: "Municipio",
  CENTRO_COORDINADOR: "Centro coordinador",
  ONG: "ONG",
};

export const managedOrganizationSchema = organizationSchema.extend({
  activa: z.boolean(),
  ong_nacional_id: z.uuid().nullable().optional(),
});

export const organizationsSchema = z.array(managedOrganizationSchema);

export const createOrganizationSchema = z.object({
  nombre: z
    .string()
    .trim()
    .min(1, "Ingresá el nombre de la organización.")
    .max(160, "El nombre no puede superar los 160 caracteres."),
  tipo: z.enum(organizationTypes),
});

export const editOrganizationSchema = createOrganizationSchema;

export type Organization = z.infer<typeof managedOrganizationSchema>;
export type CreateOrganizationForm = z.infer<typeof createOrganizationSchema>;
export type EditOrganizationForm = z.infer<typeof editOrganizationSchema>;
