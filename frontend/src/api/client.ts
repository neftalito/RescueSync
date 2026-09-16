import { z } from "zod";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

const errorResponseSchema = z.object({
  detail: z.string(),
});

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (init?.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!response.ok) {
    const parsedError = errorResponseSchema.safeParse(await parseJson(response));
    const message = parsedError.success
      ? parsedError.data.detail
      : "No pudimos completar la solicitud.";
    throw new ApiError(message, response.status);
  }
  return response;
}

export async function apiRequest<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit,
): Promise<T> {
  const response = await request(path, init);
  const parsed = schema.safeParse(await parseJson(response));
  if (!parsed.success) {
    throw new ApiError("La API devolvió una respuesta inválida.", 502);
  }
  return parsed.data;
}

export async function apiRequestVoid(
  path: string,
  init?: RequestInit,
): Promise<void> {
  await request(path, init);
}
