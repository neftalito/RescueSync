import { expect, test } from "@playwright/test";

import type { Oferta } from "../src/schemas/oferta";

const individual: Oferta = {
  id: 9,
  convocatoria_id: 5,
  emergencia_id: 31,
  ong_creadora_id: 4,
  creada_por_usuario_id: 7,
  estado: "PRESENTADA",
  version_actual: 1,
  version_bloqueo: 1,
  editable: true,
  consorcio_editable: false,
  requiere_desglose_nacional: true,
  observaciones: null,
  presentada_en: "2026-10-14T12:00:00Z",
  creada_en: "2026-10-14T12:00:00Z",
  items: [],
  participantes: [{ ong_id: 4, nombre: "Mi ONG", rol: "LIDER", confirmada: true }],
  emergencia: { zona: "Ribera", gravedad: "ALTA", descripcion: "Familias evacuadas." },
};

test.beforeEach(async ({ page }) => {
  await page.routeWebSocket("**/notificaciones/ws", () => undefined);
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({
    json: {
      usuario: {
        id: 7,
        email: "ong@example.org",
        rol: "REPRESENTANTE_ONG",
        organizacion: { id: 4, nombre: "Mi ONG", tipo: "ONG" },
        requiere_cambio_password: false,
      },
      csrf_token: "csrf-e2e",
    },
  }));
});

test("forma una propuesta de tres ONGs mediante selección múltiple con mouse y teclado", async ({ page }, testInfo) => {
  let vigente = individual;
  let recibido: unknown;
  let csrf: string | undefined;
  await page.route("**/api/v1/ofertas?*", (route) => route.fulfill({ json: [vigente] }));
  await page.route("**/api/v1/ofertas/ongs-disponibles?*", (route) => route.fulfill({
    json: [{ ong_id: 5, nombre: "Agua solidaria" }, { ong_id: 6, nombre: "Red de ayuda" }],
  }));
  await page.route("**/api/v1/ofertas/9/consorcio", async (route) => {
    recibido = route.request().postDataJSON();
    csrf = route.request().headers()["x-csrf-token"];
    vigente = {
      ...individual,
      estado: "BORRADOR",
      editable: false,
      consorcio_editable: true,
      version_actual: 2,
      version_bloqueo: 2,
      presentada_en: null,
      participantes: [
        ...(individual.participantes ?? []),
        { ong_id: 5, nombre: "Agua solidaria", rol: "MIEMBRO", confirmada: false },
        { ong_id: 6, nombre: "Red de ayuda", rol: "MIEMBRO", confirmada: false },
      ],
    };
    await route.fulfill({ json: vigente });
  });

  await page.goto("/mis-ofertas");
  await page.getByText("Alta · Ribera", { exact: true }).click();
  await page.getByRole("button", { name: "Invitar ONGs" }).click();
  await expect(page.getByRole("button", { name: "Enviar propuesta de consorcio" })).toBeDisabled();
  await page.getByRole("checkbox", { name: "Agua solidaria" }).focus();
  await page.keyboard.press("Space");
  await page.getByRole("checkbox", { name: "Red de ayuda" }).check();
  await expect(page.getByText("2 de 10 ONGs seleccionadas.")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("seleccion-consorcio.png"), fullPage: true });
  await page.getByRole("button", { name: "Enviar propuesta de consorcio" }).click();

  await expect(page.getByText("Agua solidaria · Integrante · Confirmación pendiente")).toBeVisible();
  await expect(page.getByText("Red de ayuda · Integrante · Confirmación pendiente")).toBeVisible();
  await expect(page.getByRole("button", { name: "Modificar oferta" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Rechazar o desarmar consorcio" })).toBeEnabled();
  expect(recibido).toEqual({ version_bloqueo: 1, ong_ids: [5, 6] });
  expect(csrf).toBe("csrf-e2e");
});

test("mantiene visibles las acciones bloqueadas y explica los recursos y el plazo requeridos", async ({ page }, testInfo) => {
  const ofertas: Oferta[] = [
    { ...individual, requiere_desglose_nacional: false },
    { ...individual, id: 10, editable: false, emergencia: { ...individual.emergencia, zona: "Centro" } },
  ];
  await page.route("**/api/v1/ofertas?*", (route) => route.fulfill({ json: ofertas }));
  await page.goto("/mis-ofertas");

  const sinRecursos = page.locator("details").filter({ hasText: "Alta · Ribera" });
  await sinRecursos.locator("summary").click();
  const invitarSinRecursos = sinRecursos.getByRole("button", { name: "Invitar ONGs" });
  await expect(invitarSinRecursos).toBeVisible();
  await expect(invitarSinRecursos).toBeDisabled();
  await expect(invitarSinRecursos).toHaveAccessibleDescription(/recursos del inventario nacional/i);

  const cerrada = page.locator("details").filter({ hasText: "Alta · Centro" });
  await cerrada.locator("summary").click();
  const modificar = cerrada.getByRole("button", { name: "Modificar oferta" });
  await expect(modificar).toBeVisible();
  await expect(modificar).toBeDisabled();
  await expect(modificar).toHaveAccessibleDescription(/convocatoria.*abierta/i);
  const invitarCerrada = cerrada.getByRole("button", { name: "Invitar ONGs" });
  await expect(invitarCerrada).toBeVisible();
  await expect(invitarCerrada).toBeDisabled();
  await expect(invitarCerrada).toHaveAccessibleDescription(/convocatoria.*abierta/i);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("acciones-deshabilitadas.png"), fullPage: true });
});

test("deshabilita crear oferta al volver al lote después de presentar una oferta", async ({ page }) => {
  let presentada = false;
  const oferta: Oferta = {
    ...individual,
    requiere_desglose_nacional: false,
    items: [{ id: 111, lote_id: 12, tipo: "RECURSO", descripcion: "Agua potable",
      cantidad_ofrecida: "250.000", unidad: "litros" }],
  };
  await page.route("**/api/v1/emergencias/31/lotes?*", (route) => route.fulfill({
    json: [{ id: 12, emergencia_id: 31, tipo_necesidad: "Agua potable", descripcion: null,
      cantidad_requerida: "1000.000", unidad: "litros", estado: "PUBLICADO" }],
  }));
  await page.route("**/api/v1/convocatorias", (route) => route.fulfill({
    json: [{ id: 5, emergencia_id: 31, numero: 1, estado: "ABIERTA",
      publicada_en: "2026-10-14T12:00:00Z", cierra_en: "2026-10-21T12:00:00Z",
      emergencia: individual.emergencia,
      lotes: [{ lote_id: 12, tipo_necesidad: "Agua potable", descripcion: null,
        cantidad_publicada: "1000.000", unidad_publicada: "litros" }],
    }],
  }));
  await page.route("**/api/v1/ofertas", async (route) => {
    if (route.request().method() === "POST") {
      presentada = true;
      await route.fulfill({ status: 201, json: oferta });
    } else {
      await route.fulfill({ json: presentada ? [oferta] : [] });
    }
  });

  await page.goto("/emergencias/31/lotes");
  await page.getByRole("link", { name: "Crear oferta para Agua potable" }).click();
  await page.getByLabel("Cantidad ofrecida", { exact: true }).fill("250");
  await page.getByRole("button", { name: "Presentar oferta", exact: true }).click();
  await expect(page.getByText("Oferta 9 presentada correctamente.")).toBeVisible();
  await page.goBack();

  const crear = page.getByRole("button", { name: "Crear oferta para Agua potable" });
  await expect(crear).toBeVisible();
  await expect(crear).toBeDisabled();
  await expect(crear).toHaveAccessibleDescription(/ya.*oferta para este lote/i);
  await expect(page.getByRole("link", { name: "Crear oferta para Agua potable" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
