import { expect, test, type Page } from "@playwright/test";

const ongId = "00000000-0000-4000-8000-000000000001";
const capacidadId = "00000000-0000-4000-8000-000000000002";
const recurso = {
  id: "00000000-0000-4000-8000-000000000003",
  ongId,
  capacidadId,
  codigoInterno: "AMB-01",
  nombre: "Ambulancias de rescate",
  capacidad: "Ambulancias",
  unidad: "vehículos",
  admiteFracciones: false,
  cantidadTotal: "10.000",
  cantidadComprometida: "4.000",
  cantidadDisponible: "6.000",
  activo: true,
  actualizadoEn: "2026-10-15T12:00:00Z",
};

async function simularInventario(page: Page): Promise<void> {
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
    } else if (path.endsWith("/mi-ong/conexion")) {
      await route.fulfill({
        json: {
          estado: "LISTA",
          vinculada: true,
          conectada: true,
          ongId,
          expiraEn: null,
        },
      });
    } else if (path.endsWith("/mi-ong/capacidades")) {
      await route.fulfill({
        json: [{
          id: capacidadId,
          codigo: "AMBULANCIAS",
          nombre: "Ambulancias",
          tipo: "VEHICULO",
          unidad: "vehículos",
          admiteFracciones: false,
        }],
      });
    } else if (path.endsWith("/mi-ong/recursos")) {
      await route.fulfill({ json: [recurso] });
    } else {
      await route.fulfill({ status: 404, json: { detail: "Ruta no simulada." } });
    }
  });
}

test("centra el modal, mantiene el foco y permite cancelar con teclado o botones", async ({
  page,
}, testInfo) => {
  await simularInventario(page);
  await page.goto("/mis-recursos/inventario");
  const editar = page.getByRole("button", { name: "Editar AMB-01" });
  await editar.click();
  const dialog = page.getByRole("dialog", {
    name: "Editar cantidad: Ambulancias de rescate",
  });
  await expect(dialog).toBeVisible();
  const cantidad = dialog.getByLabel(/Nuevo total/);
  await expect(cantidad).toBeFocused();
  await expect(cantidad).toHaveValue("10.000");

  const posicion = await dialog.boundingBox();
  const viewport = page.viewportSize();
  if (!posicion || !viewport) throw new Error("No se pudo medir el modal.");
  expect(Math.abs(posicion.x + posicion.width / 2 - viewport.width / 2)).toBeLessThan(2);
  expect(Math.abs(posicion.y + posicion.height / 2 - viewport.height / 2)).toBeLessThan(2);
  expect(posicion.x).toBeGreaterThanOrEqual(16);
  expect(posicion.y).toBeGreaterThanOrEqual(16);
  expect(await page.evaluate(() => document.body.style.overflow)).toBe("hidden");

  await page.getByRole("button", { name: "Registrar recurso" }).evaluate((button) => button.focus());
  await expect(cantidad).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Guardar cantidad" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Cancelar", exact: true })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "Guardar cantidad" })).toBeFocused();
  await page.screenshot({ path: testInfo.outputPath("editar-recurso-modal.png") });

  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(editar).toBeFocused();
  expect(await page.evaluate(() => document.body.style.overflow)).toBe("");
  await editar.click();
  await cantidad.fill("15");
  await dialog.getByRole("button", { name: "Cancelar", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(editar).toBeFocused();
  await editar.click();
  await expect(cantidad).toHaveValue("10.000");
  await dialog.getByRole("button", { name: "Cerrar edición" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(editar).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("conserva el modal durante el guardado y actualiza el inventario al terminar", async ({ page }) => {
  await simularInventario(page);
  let confirmarGuardado = (): void => {};
  const respuestaPendiente = new Promise<void>((resolve) => {
    confirmarGuardado = resolve;
  });
  const actualizado = { ...recurso, cantidadTotal: "12.000", cantidadDisponible: "8.000" };
  await page.route(`**/mi-ong/recursos/${recurso.id}`, async (route) => {
    expect(route.request().postDataJSON()).toEqual({
      cantidadTotal: "12",
      actualizadoEn: recurso.actualizadoEn,
    });
    await respuestaPendiente;
    await page.route("**/mi-ong/recursos", (consulta) => consulta.fulfill({ json: [actualizado] }));
    await route.fulfill({ json: actualizado });
  });

  try {
    await page.goto("/mis-recursos/inventario");
    await page.getByRole("button", { name: "Editar AMB-01" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel(/Nuevo total/).fill("12");
    await dialog.getByRole("button", { name: "Guardar cantidad" }).click();
    await expect(dialog.getByRole("button", { name: "Guardando…" })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "Cancelar", exact: true })).toBeDisabled();
    await expect(dialog.getByRole("button", { name: "Cerrar edición" })).toBeDisabled();
    await expect(dialog.getByLabel(/Nuevo total/)).toBeDisabled();
    await page.keyboard.press("Escape");
    await expect(dialog).toBeVisible();
    confirmarGuardado();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("status")).toHaveText("Cantidad actualizada.");
    await expect(page.getByText("12,00", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Editar AMB-01" })).toBeFocused();
  } finally {
    confirmarGuardado();
  }
});
