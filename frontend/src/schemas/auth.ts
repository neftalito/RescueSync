import { z } from "zod";

export const roles = [
  "OPERADOR_MUNICIPAL",
  "COORDINADOR_REGIONAL",
  "REPRESENTANTE_ONG",
  "AUDITOR_DIRECTIVO",
] as const;

export type Role = (typeof roles)[number];

export const roleLabels: Record<Role, string> = {
  OPERADOR_MUNICIPAL: "Operador municipal",
  COORDINADOR_REGIONAL: "Centro coordinador regional",
  REPRESENTANTE_ONG: "Representante de ONG",
  AUDITOR_DIRECTIVO: "Auditor / Directivo",
};

export const loginSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Ingresá tu correo electrónico.")
    .email("Ingresá un correo electrónico válido."),
  password: z
    .string()
    .min(1, "Ingresá tu contraseña.")
    .max(128, "La contraseña no puede superar los 128 caracteres."),
});

const organizationSchema = z.object({
  id: z.number().int().positive(),
  nombre: z.string(),
  tipo: z.enum(["MUNICIPIO", "CENTRO_COORDINADOR", "ONG"]),
});

export const sessionSchema = z.object({
  usuario: z.object({
    id: z.number().int().positive(),
    email: z.string().email(),
    rol: z.enum(roles),
    organizacion: organizationSchema.nullable(),
  }),
  csrf_token: z.string().min(1),
});

export type LoginCredentials = z.infer<typeof loginSchema>;
export type Session = z.infer<typeof sessionSchema>;
