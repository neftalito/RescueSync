import { readFile } from "node:fs/promises";
import { expect, test, type Page, type WebSocketRoute } from "@playwright/test";

async function simularApi(
  page: Page,
  rol = "AUDITOR_DIRECTIVO",
  alConectar?: (socket: WebSocketRoute) => void,
): Promise<void> {
  await page.routeWebSocket(
    "**/notificaciones/ws",
    alConectar ?? (() => undefined),
  );
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const filtros = {
      fecha_desde: url.searchParams.get("fecha_desde") ?? "2026-10-01",
      fecha_hasta: url.searchParams.get("fecha_hasta") ?? "2026-10-15",
      municipio_id: null,
      gravedad: null,
      estado: null,
    };
    if (url.pathname.endsWith("/auth/me")) {
      await route.fulfill({
        json: {
          usuario: {
            id: 7,
            email: "auditor@rescuesync.org",
            rol,
            organizacion: null,
            requiere_cambio_password: false,
          },
          csrf_token: "csrf-e2e",
        },
      });
    } else if (url.pathname.endsWith("/metricas/tiempos")) {
      await route.fulfill({
        json: {
          generado_en: "2026-10-15T12:00:00Z",
          filtros,
          disponibilidad: "PARCIAL",
          casos_seleccionados: 2,
          casos_vinculados: 1,
          casos_consultados: 1,
          casos_con_muestras: 1,
          casos_sin_historial_suficiente: 1,
          casos_con_error: 0,
          muestras_descartadas: 0,
          etapas: [
            {
              etapa: "Generar lotes de necesidades",
              version_proceso: "1.2",
              promedio_segundos: 7200,
              muestras: 3,
            },
          ],
        },
      });
    } else if (url.pathname.endsWith("/metricas")) {
      await route.fulfill({
        json: {
          generado_en: "2026-10-15T12:00:00Z",
          filtros,
          municipios: [{ id: 1, nombre: "Municipio del Delta" }],
          resumen: {
            emergencias: 2,
            activas: 1,
            resueltas: 1,
            convocatorias_abiertas: 1,
            ofertas_presentadas: 3,
            ong_participantes: 2,
          },
          por_estado: [
            { categoria: "PUBLICADA", cantidad: 1 },
            { categoria: "RESUELTA", cantidad: 1 },
          ],
          por_gravedad: [{ categoria: "ALTA", cantidad: 2 }],
          evolucion_mensual: [
            { categoria: "2026-09", cantidad: 1 },
            { categoria: "2026-10", cantidad: 1 },
          ],
          tipos_oferta: [
            { categoria: "INDIVIDUAL", cantidad: 2 },
            { categoria: "CONJUNTA", cantidad: 1 },
          ],
          cantidades_ofrecidas: [
            {
              capacidad: "Agua potable",
              codigo_capacidad: "AGUA",
              cantidad: "3000.000",
              unidad: "litros",
            },
          ],
        },
      });
    } else {
      await route.fulfill({ json: [] });
    }
  });
}

test("auditor usa gráficos, filtros y exportaciones sin desbordamiento", async ({
  page,
}, testInfo) => {
  await simularApi(page);
  const errores: string[] = [];
  page.on("pageerror", (error) => errores.push(error.message));
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Dashboard de auditoría" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Exportar" })).toBeEnabled();
  await expect(page.locator(".recharts-surface").first()).toBeVisible();
  await expect(
    page
      .locator(
        '[data-reporte-grafico="Emergencias por gravedad"] .recharts-sector',
      )
      .first(),
  ).toHaveAttribute("fill", "#ea580c");
  await expect(
    page.getByText("Historial parcial", { exact: true }),
  ).toBeVisible();
  await page.getByText("Ver datos de emergencias por estado").click();
  await expect(
    page.getByRole("table", { name: "Emergencias por estado" }),
  ).toContainText("Resuelta");
  await page.getByLabel("Desde", { exact: true }).fill("2026-09-01");
  const consulta = page.waitForRequest(
    (request) =>
      request.url().includes("/metricas?") &&
      request.url().includes("fecha_desde=2026-09-01"),
  );
  await page.getByRole("button", { name: "Aplicar filtros" }).click();
  await consulta;
  await expect(page.getByRole("button", { name: "Exportar" })).toBeEnabled();
  const descargado = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exportar" }).click();
  await page.getByRole("button", { name: "Exportar JSON" }).click();
  const archivo = await (await descargado).path();
  if (archivo === null) throw new Error("No se descargó el reporte JSON.");
  const contenido = await readFile(archivo, "utf-8");
  expect(contenido).toContain('"fecha_desde": "2026-09-01"');
  expect(contenido).toContain('"bonita": "PARCIAL"');
  const csvDescargado = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exportar" }).click();
  await page.getByRole("button", { name: "Exportar CSV" }).click();
  const csv = await (await csvDescargado).path();
  if (csv === null) throw new Error("No se descargó el reporte CSV.");
  expect(await readFile(csv, "utf-8")).toContain('"3000.000","litros"');
  const pdfDescargado = page.waitForEvent("download");
  await page.getByRole("button", { name: "Exportar" }).click();
  await page.getByRole("button", { name: "Exportar PDF" }).click();
  const pdf = await (await pdfDescargado).path();
  if (pdf === null) throw new Error("No se descargó el reporte PDF.");
  const pdfBuffer = await readFile(pdf);
  expect(pdfBuffer.subarray(0, 5).toString()).toBe("%PDF-");
  expect(pdfBuffer.length).toBeGreaterThan(5000);
  expect(pdfBuffer.toString("latin1")).toContain("/Subtype /Image");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  expect(errores).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("dashboard-auditor.png"),
    fullPage: true,
  });
});

test("un evento WebSocket vuelve a consultar el dashboard con los filtros elegidos", async ({
  page,
}) => {
  let socket: WebSocketRoute | undefined;
  await simularApi(page, "AUDITOR_DIRECTIVO", (conectado) => {
    socket = conectado;
  });
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Exportar" })).toBeEnabled();
  await page.getByLabel("Desde", { exact: true }).fill("2026-09-01");
  await page.getByRole("button", { name: "Aplicar filtros" }).click();
  await expect(page.getByRole("button", { name: "Exportar" })).toBeEnabled();
  await expect.poll(() => socket !== undefined).toBe(true);
  const consulta = page.waitForRequest(
    (request) =>
      request.url().includes("/metricas?") &&
      request.url().includes("fecha_desde=2026-09-01"),
  );
  if (!socket) throw new Error("No se abrió el WebSocket.");
  socket.send(JSON.stringify({ evento: "metricas.actualizadas" }));
  await consulta;
  await expect(page.getByLabel("Desde", { exact: true })).toHaveValue(
    "2026-09-01",
  );
});

test("administrador no recibe el dashboard ni consulta métricas", async ({
  page,
}) => {
  await simularApi(page, "ADMINISTRADOR");
  const consultas: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/metricas")) consultas.push(request.url());
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Bienvenido a RescueSync" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Panel de indicadores" }),
  ).toHaveCount(0);
  expect(consultas).toEqual([]);
});
