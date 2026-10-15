import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { type ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { emergenciasQueryKey } from "./useEmergencias";
import { notificacionesQueryKey } from "./useNotificaciones";
import { useNotificacionesTiempoReal } from "./useNotificacionesTiempoReal";

class WebSocketFalso {
  static ultimo: WebSocketFalso | null = null;

  readonly url: string;
  onopen: ((evento: Event) => void) | null = null;
  onmessage: ((evento: MessageEvent<unknown>) => void) | null = null;
  onclose: ((evento: CloseEvent) => void) | null = null;

  constructor(url: string | URL) {
    this.url = String(url);
    WebSocketFalso.ultimo = this;
  }

  close(): void {
    this.onclose?.(new CloseEvent("close", { code: 1000 }));
  }

  emitir(payload: unknown): void {
    this.onmessage?.(
      new MessageEvent("message", { data: JSON.stringify(payload) }),
    );
  }
}

function Probe(): ReactElement | null {
  useNotificacionesTiempoReal(true);
  return null;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  WebSocketFalso.ultimo = null;
});

describe("useNotificacionesTiempoReal", () => {
  it("refresca las métricas al reconectar y al recibir un cambio sin tocar los filtros", async () => {
    vi.stubGlobal("WebSocket", WebSocketFalso);
    const queryClient = new QueryClient();
    const key = [
      "metricas",
      "locales",
      { fecha_desde: "2026-09-01", estado: "PUBLICADA" },
    ];
    queryClient.setQueryData(key, { emergencias: 2 });
    const invalidar = vi.spyOn(queryClient, "invalidateQueries");
    render(
      <QueryClientProvider client={queryClient}>
        <Probe />
      </QueryClientProvider>,
    );
    const socket = WebSocketFalso.ultimo;
    if (!socket) throw new Error("No se creó el socket.");
    act(() => {
      socket.onopen?.(new Event("open"));
      socket.emitir({ evento: "metricas.actualizadas" });
    });
    await waitFor(() =>
      expect(invalidar).toHaveBeenCalledWith({ queryKey: ["metricas"] }),
    );
    expect(queryClient.getQueryState(key)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryData(key)).toEqual({ emergencias: 2 });
    expect(queryClient.getQueryData(notificacionesQueryKey)).toBeUndefined();
  });
  it("incorpora la novedad e invalida la bandeja correspondiente", async () => {
    vi.stubGlobal("WebSocket", WebSocketFalso);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidar = vi.spyOn(queryClient, "invalidateQueries");
    render(
      <QueryClientProvider client={queryClient}>
        <Probe />
      </QueryClientProvider>,
    );
    const socket = WebSocketFalso.ultimo;
    if (socket === null)
      throw new Error("No se creó el WebSocket de novedades.");

    act(() => {
      socket.emitir({
        evento: "notificacion.creada",
        notificacion: {
          id: 51,
          usuario_id: 7,
          tipo: "EMERGENCIA_REGISTRADA",
          titulo: "Nueva emergencia pendiente",
          mensaje: "Se registró una emergencia en Ribera norte.",
          ruta: "/emergencias/31/lotes",
          leida_en: null,
          creada_en: "2026-09-28T18:20:39.102766Z",
        },
      });
    });

    await waitFor(() => {
      expect(queryClient.getQueryData(notificacionesQueryKey)).toEqual([
        expect.objectContaining({ id: 51 }),
      ]);
      expect(invalidar).toHaveBeenCalledWith({ queryKey: emergenciasQueryKey });
    });
    expect(socket.url).toBe("ws://localhost:8000/api/v1/notificaciones/ws");
  });
});
