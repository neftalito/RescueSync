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
          casos_activos_consultados: 1,
          casos_activos_con_error: 0,
          actividad_por_etapa: [{ etapa: "Revisar necesidades", version_proceso: "1.2", tareas: 1, con_fecha: 1, promedio_antiguedad_segundos: 3600, vencidas: 1, sin_plazo: 0, fallidas: 0 }],
          tareas_activas: [{ emergencia_id: 9, municipio_id: 1, gravedad: "ALTA", case_id: 42, tarea_id: 7, etapa: "Revisar necesidades", version_proceso: "1.2", estado: "ready", desde_en: "2026-10-15T09:00:00Z", antiguedad_segundos: 3600, vence_en: "2026-10-15T09:30:00Z", vencida: true }],
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
          filtros: {
            ...filtros,
            umbral_aportes_horas: Number(url.searchParams.get("umbral_aportes_horas") ?? 24),
            umbral_resolucion_horas: Number(url.searchParams.get("umbral_resolucion_horas") ?? 72),
          },
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
          indicadores_proceso: {
            emergencias_con_hechos: 1, emergencias_sin_hechos: 1,
            resolucion_por_gravedad: [{ gravedad: "ALTA", emergencias: 2, resueltas: 1, cierres_confirmados: 1, resueltas_sin_cierre: 0, cierres_con_tiempo: 1, dentro_del_umbral: 1, tasa_resolucion: 50, tasa_dentro_del_umbral: 100, promedio_segundos: 7200, promedio_dentro_del_umbral_segundos: 7200 }],
            reiteradas: [{ emergencia_id: 9, reaperturas: 1, reformulaciones: 0 }],
            ranking_ongs: [{ ong_id: 4, ong: "Ayuda", capacidad: "AGUA", unidad: "litros", cantidad: "100.125", aportes: 1, finalizados: 1, finalizados_con_tiempo: 1, dentro_del_umbral: 1, tasa_dentro_del_umbral: 100 }],
            cobertura_cierres: { total: 1, parcial: 0, proporcion_total: 100, proporcion_parcial: 0 },
            suministros_movilizados: {
              cantidades: [{ capacidad: "AGUA", unidad: "litros", cantidad: "90.125" }],
              participaciones_con_registro: 1, participaciones_sin_registro: 0,
            },
            resolucion_consorcios: { con_consorcio: 1, con_adjudicacion_verificable: 1, sin_adjudicacion_verificable: 0, proporcion: 100 },
            demanda_rubros: [{ capacidad: "AGUA", unidad: "litros", cantidad: "200.250" }],
            alerta_adjudicacion_promedio_segundos: 3600, alerta_adjudicacion_muestras: 1,
            definiciones: ["Se seleccionan emergencias por fecha de alta."],
          },
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
  await page.getByLabel("Umbral de finalización de aportes").selectOption("12");
  await page.getByLabel("Umbral de resolución de emergencias").selectOption("720");
  const consulta = page.waitForRequest(
    (request) =>
      request.url().includes("/metricas?") &&
      request.url().includes("fecha_desde=2026-09-01") &&
      request.url().includes("umbral_aportes_horas=12") &&
      request.url().includes("umbral_resolucion_horas=720"),
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
  expect(contenido).toContain('"umbral_aportes_horas": 12');
  expect(contenido).toContain('"umbral_resolucion_horas": 720');
  expect(contenido).toContain('"bonita": "PARCIAL"');
  expect(contenido).toContain('"cantidad": "100.125"');
  await expect(page.getByRole("heading", { name: "Resultados del proceso" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Finalizados en hasta 12 h" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Cierres en hasta 1 mes (30 días)" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Suministros movilizados" })).toContainText("90.125");
  await expect(page.getByText(/1 de 1 cierres con adjudicación verificable/)).toBeVisible();
  await expect(page.getByRole("table", { name: "Tareas en ejecución y pendientes" })).toContainText("Revisar necesidades");
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

test("los iconos del header muestran novedades y resaltan hover y pulsación", async ({
  page,
}) => {
  await simularApi(page);
  await page.route("**/api/v1/notificaciones", (route) =>
    route.fulfill({
      json: [
        {
          id: 41,
          usuario_id: 7,
          tipo: "TAREA_BONITA_FALLIDA",
          titulo: "Tarea de Bonita con errores",
          mensaje: "Una tarea requiere revisión.",
          ruta: "/",
          leida_en: null,
          creada_en: "2026-10-15T12:00:00Z",
        },
      ],
    }),
  );
  await page.route("**/api/v1/notificaciones/leidas", (route) =>
    route.fulfill({
      json: {
        cantidad_actualizada: 1,
        leida_en: "2026-10-15T12:01:00Z",
      },
    }),
  );
  await page.goto("/");
  const campana = page.getByRole("button", {
    name: "Notificaciones",
    exact: true,
  });
  const salir = page.getByRole("button", {
    name: "Cerrar sesión",
    exact: true,
  });
  const opciones = page.getByRole("link", { name: "Opciones", exact: true });
  const colorTema = async (nombre: string): Promise<string> =>
    page.evaluate((color) => {
      const referencia = document.createElement("span");
      referencia.style.color = `var(--color-${color})`;
      document.body.append(referencia);
      const valor = getComputedStyle(referencia).color;
      referencia.remove();
      return valor;
    }, nombre);
  await expect(campana).toHaveAccessibleDescription("1 notificación sin leer");
  const emblema = campana.getByText("1", { exact: true });
  await expect(emblema).toBeVisible();
  await expect(emblema).toHaveAttribute("aria-hidden", "true");
  await expect(campana).toHaveAttribute("aria-expanded", "false");
  expect(await salir.textContent()).toBe("");
  expect(await opciones.textContent()).toBe("");
  const posicionSalida = await salir.boundingBox();
  const posicionOpciones = await opciones.boundingBox();
  const posicionCampana = await campana.boundingBox();
  const anchoPantalla = page.viewportSize()?.width;
  if (
    !posicionSalida ||
    !posicionOpciones ||
    !posicionCampana ||
    !anchoPantalla
  ) {
    throw new Error(
      "No se pudo medir la posición de los accesos del encabezado.",
    );
  }
  expect(
    anchoPantalla - posicionSalida.x - posicionSalida.width,
  ).toBeLessThanOrEqual(24);
  expect(posicionSalida.y).toBeLessThanOrEqual(20);
  expect(
    posicionOpciones.y > posicionSalida.y + posicionSalida.height ||
      posicionSalida.x - posicionOpciones.x - posicionOpciones.width >= 40,
  ).toBe(true);
  await expect(campana.locator("svg")).toHaveAttribute(
    "data-estado",
    "sonando",
  );
  await campana.hover();
  await expect(campana).toHaveCSS(
    "outline-color",
    await colorTema("yellow-500"),
  );
  await expect(campana).toHaveCSS("outline-width", "2px");
  await page.mouse.down();
  await expect(campana).toHaveCSS(
    "outline-color",
    await colorTema("yellow-700"),
  );
  await page.mouse.up();
  await page.getByRole("button", { name: "Marcar todas como vistas" }).click();
  await expect(campana).toHaveAccessibleDescription(
    "No hay notificaciones sin leer",
  );
  await expect(campana.locator("svg")).toHaveAttribute("data-estado", "quieta");
  await expect(emblema).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(campana).toBeFocused();
  await salir.hover();
  await expect(salir).toHaveCSS("outline-color", await colorTema("red-500"));
  await page.mouse.down();
  await expect(salir).toHaveCSS("outline-color", await colorTema("red-700"));
  // Soltar fuera evita cerrar la sesión durante la comprobación visual.
  await page.mouse.move(0, 0);
  await page.mouse.up();
  await opciones.hover();
  await expect(opciones).toHaveCSS(
    "outline-color",
    await colorTema("gray-500"),
  );
  await expect(opciones).toHaveCSS("outline-width", "2px");
  await page.mouse.down();
  await expect(opciones).toHaveCSS(
    "outline-color",
    await colorTema("gray-700"),
  );
  await page.mouse.up();
  await expect(page).toHaveURL(/\/opciones$/);
  await expect(
    page.getByRole("heading", { name: "Opciones", level: 1 }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Cambiar contraseña" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("Opciones permite cambiar la contraseña y conserva el encabezado en móvil y escritorio", async ({
  page,
}, testInfo) => {
  await simularApi(page);
  await page.route("**/api/v1/auth/password", async (route) => {
    expect(route.request().headers()["x-csrf-token"]).toBe("csrf-e2e");
    expect(route.request().postDataJSON()).toEqual({
      password_actual: "Una-clave-actual",
      password_nueva: "Una-clave-nueva-2026",
    });
    await route.fulfill({
      json: {
        usuario: {
          id: 7,
          email: "auditor@rescuesync.org",
          rol: "AUDITOR_DIRECTIVO",
          organizacion: null,
          requiere_cambio_password: false,
        },
        csrf_token: "csrf-renovado-e2e",
      },
    });
  });
  await page.goto("/cambiar-password");
  await expect(page).toHaveURL(/\/opciones$/);
  await page
    .getByLabel("Contraseña actual", { exact: true })
    .fill("Una-clave-actual");
  await page
    .getByLabel("Contraseña nueva", { exact: true })
    .fill("Una-clave-nueva-2026");
  await page
    .getByLabel("Repetir contraseña nueva")
    .fill("Una-clave-nueva-2026");
  await page.getByRole("button", { name: "Guardar contraseña" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Contraseña actualizada.",
  );
  await expect(page).toHaveURL(/\/opciones$/);
  await expect(
    page.getByLabel("Contraseña actual", { exact: true }),
  ).toHaveValue("");
  await expect(
    page.getByRole("button", { name: "Cerrar sesión", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("opciones.png"),
    fullPage: true,
  });
  await page.getByRole("link", { name: "Volver al inicio" }).click();
  await expect(
    page.getByRole("heading", { name: "Dashboard de auditoría" }),
  ).toBeVisible();
});
