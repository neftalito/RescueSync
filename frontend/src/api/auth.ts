import {
  sessionSchema,
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
