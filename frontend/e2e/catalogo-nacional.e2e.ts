import { expect, test } from "@playwright/test";

const capacidad = {
  id: "00000000-0000-4000-8000-000000000101",
  codigo: "ATENCION-MEDICA",
  nombre: "Atención médica",
  tipo: "PERSONAL",
  unidad: "personas",
  admiteFracciones: false,
};

test.beforeEach(async ({ page }) => {
  await page.routeWebSocket("**/notificaciones/ws", () => undefined);
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({
    json: {
      usuario: {
        id: 7, email: "admin@example.org", rol: "ADMINISTRADOR",
        organizacion: null, requiere_cambio_password: false,
      },
      csrf_token: "csrf-e2e",
    },
  }));
  await page.route("**/api/v1/notificaciones*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/v1/catalogo-nacional/unidades", (route) => route.fulfill({
    json: [{ codigo: "personas", nombre: "Personas" }],
  }));
});

test("genera el código desde el nombre, crea la capacidad y bloquea un duplicado", async ({ page }, testInfo) => {
  let creada = false;
  let altas = 0;
  await page.route("**/api/v1/catalogo-nacional/capacidades", async (route) => {
    if (route.request().method() === "POST") {
      altas += 1;
      expect(route.request().headers()["x-csrf-token"]).toBe("csrf-e2e");
      expect(route.request().postDataJSON()).toEqual({
        codigo: "ATENCION-MEDICA", nombre: "Atención médica", tipo: "PERSONAL",
        unidad: "personas", admiteFracciones: false,
      });
      creada = true;
      await route.fulfill({ status: 201, json: capacidad });
    } else {
      await route.fulfill({ json: creada ? [capacidad] : [] });
    }
  });
  await page.goto("/catalogo-nacional");
  await page.getByLabel("Nombre de la capacidad").fill("Atención médica");
  await expect(page.getByLabel("Código", { exact: true })).toHaveValue("ATENCION-MEDICA");
  await expect(page.getByLabel("Código", { exact: true })).not.toBeEditable();
  await page.getByLabel("Tipo de recurso").selectOption("PERSONAL");
  await page.getByLabel("Unidad", { exact: true }).selectOption("personas");
  await page.getByRole("button", { name: "Crear capacidad", exact: true }).click();
  await expect(page.getByRole("status")).toHaveText("Capacidad «Atención médica» creada.");
  await expect(page.getByLabel("Código", { exact: true })).toHaveValue("");
  await expect(page.getByRole("heading", { name: "Atención médica", exact: true })).toBeVisible();

  await page.getByLabel("Nombre de la capacidad").fill("Atención  médica");
  await expect(page.getByRole("button", { name: "Crear capacidad", exact: true })).toBeDisabled();
  await expect(page.getByLabel("Código", { exact: true })).toHaveAccessibleDescription(/Ya existe una capacidad.*ATENCION-MEDICA/);
  expect(altas).toBe(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("codigo-automatico.png"), fullPage: true });
});

test("conserva los datos y explica cómo resolver un conflicto devuelto por la API", async ({ page }) => {
  await page.route("**/api/v1/catalogo-nacional/capacidades", (route) => route.fulfill(
    route.request().method() === "POST"
      ? { status: 409, json: { detail: "Ya existe una capacidad con ese código." } }
      : { json: [] },
  ));
  await page.goto("/catalogo-nacional");
  await page.getByLabel("Nombre de la capacidad").fill("Atención médica");
  await page.getByLabel("Tipo de recurso").selectOption("PERSONAL");
  await page.getByLabel("Unidad", { exact: true }).selectOption("personas");
  await page.getByRole("button", { name: "Crear capacidad", exact: true }).click();

  await expect(page.getByRole("alert")).toHaveText("Ya existe una capacidad con ese código. Cambiá el nombre para generar otro código.");
  await expect(page.getByLabel("Nombre de la capacidad")).toHaveValue("Atención médica");
  await expect(page.getByLabel("Código", { exact: true })).toHaveValue("ATENCION-MEDICA");
});
