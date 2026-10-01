import {
  organizationsSchema,
  userSchema,
  usersSchema,
  type CreateUserForm,
  type EditUserForm,
  type ManagedUser,
  type Organization,
  type ResetPasswordForm,
} from "../schemas/users";
import type { Role } from "../schemas/auth";
import { apiRequest, apiRequestVoid } from "./client";

function organizationId(value: string, role: Role): number | null {
  if (role === "AUDITOR_DIRECTIVO" || role === "ADMINISTRADOR") return null;
  return value === "" ? null : Number(value);
}

export function getUsers(): Promise<ManagedUser[]> {
  return apiRequest("/usuarios", usersSchema);
}

export function getOrganizations(): Promise<Organization[]> {
  return apiRequest("/organizaciones", organizationsSchema);
}

export function createUser(
  values: CreateUserForm,
  csrfToken: string,
): Promise<ManagedUser> {
  return apiRequest("/usuarios", userSchema, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify({
      email: values.email,
      rol: values.rol,
      organizacion_id: organizationId(values.organizacion_id, values.rol),
    }),
  });
}

export function updateUser(
  userId: number,
  values: EditUserForm & { activo?: boolean },
  csrfToken: string,
): Promise<ManagedUser> {
  return apiRequest(`/usuarios/${userId}`, userSchema, {
    method: "PATCH",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify({
      ...values,
      organizacion_id: organizationId(values.organizacion_id, values.rol),
    }),
  });
}

export function deactivateUser(
  userId: number,
  csrfToken: string,
): Promise<void> {
  return apiRequestVoid(`/usuarios/${userId}`, {
    method: "DELETE",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function reactivateUser(
  userId: number,
  csrfToken: string,
): Promise<ManagedUser> {
  return apiRequest(`/usuarios/${userId}`, userSchema, {
    method: "PATCH",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ activo: true }),
  });
}

export function resetUserPassword(
  userId: number,
  values: ResetPasswordForm,
  csrfToken: string,
): Promise<ManagedUser> {
  return apiRequest(`/usuarios/${userId}/password`, userSchema, {
    method: "PUT",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ password: values.password }),
  });
}
