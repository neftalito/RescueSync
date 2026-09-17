import {
  sessionSchema,
  type ChangePasswordForm,
  type LoginCredentials,
  type Session,
} from "../schemas/auth";
import { apiRequest, apiRequestVoid } from "./client";

export function login(credentials: LoginCredentials): Promise<Session> {
  return apiRequest("/auth/login", sessionSchema, {
    method: "POST",
    body: JSON.stringify(credentials),
  });
}

export function getSession(): Promise<Session> {
  return apiRequest("/auth/me", sessionSchema);
}

export function logout(csrfToken: string): Promise<void> {
  return apiRequestVoid("/auth/logout", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function changePassword(
  values: ChangePasswordForm,
  csrfToken: string,
): Promise<Session> {
  return apiRequest("/auth/password", sessionSchema, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify({
      password_actual: values.password_actual,
      password_nueva: values.password_nueva,
    }),
  });
}
