import { expect, test } from "@playwright/test";

// Valida el contorno real, el foco y el espacio táctil en ambos tamaños de pantalla.
test("permite reconocer y usar las acciones con íconos mediante mouse y teclado", async ({
  page,
}, testInfo) => {
  await page.routeWebSocket("**/notificaciones/ws", () => undefined);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) {
      await route.fulfill({
        json: {
          usuario: {
            id: 7,
            email: "ong@rescuesync.org",
            rol: "REPRESENTANTE_ONG",
            organizacion: { id: 4, nombre: "ONG de prueba", tipo: "ONG" },
            requiere_cambio_password: false,
          },
          csrf_token: "csrf-e2e",
        },
      });
    } else if (path.endsWith("/notificaciones")) {
      await route.fulfill({ json: [] });
    } else {
      await route.fulfill({ status: 404, json: { detail: "Ruta no simulada." } });
    }
  });

  await page.goto("/opciones");
  const inicio = page.getByRole("link", { name: "Volver al inicio" });
  await expect(inicio).toBeVisible();
  await expect(inicio).toHaveAttribute("title", "Volver al inicio");
  await expect(inicio.locator("svg")).toHaveAttribute("aria-hidden", "true");
  await expect(inicio.locator(".sr-only")).toHaveText("Volver al inicio");
  const area = await inicio.boundingBox();
  expect(area?.width).toBe(44);
  expect(area?.height).toBe(44);
  await expect(inicio).toHaveCSS("border-top-width", "1px");
  await inicio.hover();
  await expect(inicio).not.toHaveCSS("outline-color", "rgba(0, 0, 0, 0)");
  await expect(inicio).toHaveCSS("outline-width", "2px");
  await page.mouse.move(0, 0);
  await inicio.focus();
  await page.keyboard.press("Tab");
  await page.keyboard.press("Shift+Tab");
  await expect(inicio).toBeFocused();
  await expect(inicio).not.toHaveCSS("outline-color", "rgba(0, 0, 0, 0)");

  const actual = page.getByLabel("Contraseña actual", { exact: true });
  await actual.fill("Clave-actual-2026");
  const cancelar = page.getByRole("button", { name: "Cancelar", exact: true });
  await expect(cancelar.locator("svg")).toBeVisible();
  await cancelar.click();
  await expect(actual).toHaveValue("");
  const guardar = page.getByRole("button", { name: "Guardar contraseña" });
  await expect(guardar).toBeVisible();
  const tipografiaEnlace = await inicio.evaluate((link) => ({
    size: getComputedStyle(link).fontSize,
    weight: getComputedStyle(link).fontWeight,
  }));
  await expect(guardar).toHaveCSS("font-size", tipografiaEnlace.size);
  await expect(guardar).toHaveCSS("font-weight", tipografiaEnlace.weight);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("botones-opciones.png"), fullPage: true });

  await inicio.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Bienvenido a RescueSync" })).toBeVisible();
});
