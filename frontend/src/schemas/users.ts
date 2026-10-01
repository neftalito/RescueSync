import { z } from "zod";

import { organizationSchema, roles } from "./auth";

export const userSchema = z.object({
  id: z.number().int().positive(),
  email: z.string().email(),
  rol: z.enum(roles),
  organizacion: organizationSchema.nullable(),
  activo: z.boolean(),
  requiere_cambio_password: z.boolean(),
  creado_en: z.string().datetime(),
  actualizado_en: z.string().datetime(),
});

export const usersSchema = z.array(userSchema);
export const organizationsSchema = z.array(organizationSchema);

const userFields = {
  email: z
    .string()
    .trim()
    .min(1, "Ingresá el correo electrónico.")
    .email("Ingresá un correo electrónico válido."),
  rol: z.enum(roles),
  organizacion_id: z.string(),
};

export const createUserSchema = z.object(userFields);

export const editUserSchema = z.object(userFields);

export const resetPasswordSchema = z
  .object({
    password: z
      .string()
      .min(8, "La contraseña temporal debe tener al menos 8 caracteres.")
      .max(128, "La contraseña no puede superar los 128 caracteres."),
    confirmacion: z.string().min(1, "Repetí la contraseña temporal."),
  })
  .refine((data) => data.password === data.confirmacion, {
    message: "Las contraseñas no coinciden.",
    path: ["confirmacion"],
  });

export type Organization = z.infer<typeof organizationSchema>;
export type ManagedUser = z.infer<typeof userSchema>;
export type CreateUserForm = z.infer<typeof createUserSchema>;
export type EditUserForm = z.infer<typeof editUserSchema>;
export type ResetPasswordForm = z.infer<typeof resetPasswordSchema>;
