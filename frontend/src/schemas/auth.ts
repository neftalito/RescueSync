import { z } from "zod";

export const roles = [
  "OPERADOR_MUNICIPAL",
  "COORDINADOR_REGIONAL",
  "REPRESENTANTE_ONG",
  "AUDITOR_DIRECTIVO",
  "ADMINISTRADOR",
] as const;

export type Role = (typeof roles)[number];

export const roleLabels: Record<Role, string> = {
  OPERADOR_MUNICIPAL: "Operador municipal",
  COORDINADOR_REGIONAL: "Centro coordinador regional",
  REPRESENTANTE_ONG: "Representante de ONG",
  AUDITOR_DIRECTIVO: "Auditor / Directivo",
  ADMINISTRADOR: "Administrador",
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

export const organizationSchema = z.object({
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
    requiere_cambio_password: z.boolean(),
  }),
  csrf_token: z.string().min(1),
});

export type LoginCredentials = z.infer<typeof loginSchema>;
export type Session = z.infer<typeof sessionSchema>;

export const changePasswordSchema = z
  .object({
    password_actual: z
      .string()
      .min(8, "La contraseña actual debe tener al menos 8 caracteres.")
      .max(128, "La contraseña no puede superar los 128 caracteres."),
    password_nueva: z
      .string()
      .min(8, "La contraseña nueva debe tener al menos 8 caracteres.")
      .max(128, "La contraseña no puede superar los 128 caracteres."),
    confirmacion: z.string().min(1, "Repetí la contraseña nueva."),
  })
  .refine((data) => data.password_nueva === data.confirmacion, {
    message: "Las contraseñas nuevas no coinciden.",
    path: ["confirmacion"],
  })
  .refine((data) => data.password_actual !== data.password_nueva, {
    message: "La contraseña nueva debe ser diferente de la actual.",
    path: ["password_nueva"],
  });

export type ChangePasswordForm = z.infer<typeof changePasswordSchema>;
