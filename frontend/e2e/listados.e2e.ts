import { expect, test } from "@playwright/test";

test("carga emergencias al desplazar su listado sin descargar todas al entrar", async ({ page }) => {
  const offsets: number[] = [];
  const emergencias = Array.from({ length: 45 }, (_, indice) => ({
    id: indice + 1, municipio_id: 1, centro_coordinador_id: null,
    creada_por_usuario_id: 1, gravedad: "ALTA", zona: `Zona ${indice + 1}`,
    descripcion: "Familias evacuadas.", estado: "REGISTRADA", tiene_lotes: false,
    bonita_sync: "PENDIENTE", bonita_process_instance_id: null,
    bonita_ultimo_error: null, bonita_ultimo_intento_en: null,
    creada_en: "2026-10-15T10:00:00Z", actualizada_en: "2026-10-15T10:00:00Z",
  }));
  await page.routeWebSocket("**/notificaciones/ws", () => undefined);
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/auth/me")) {
      await route.fulfill({
        json: {
          usuario: {
            id: 1, email: "municipio@example.org", rol: "OPERADOR_MUNICIPAL",
            organizacion: { id: 1, nombre: "Municipio", tipo: "MUNICIPIO" },
            requiere_cambio_password: false,
          }, csrf_token: "csrf-e2e",
        }
      });
    } else if (url.pathname.endsWith("/emergencias")) {
      const offset = Number(url.searchParams.get("offset"));
      const limit = Number(url.searchParams.get("limit"));
      offsets.push(offset);
      expect(limit).toBe(21);
      await route.fulfill({ json: emergencias.slice(offset, offset + limit) });
    } else {
      await route.fulfill({ json: [] });
    }
  });
  await page.goto("/mis-emergencias");
  const listado = page.getByRole("region", { name: "Listado de mis emergencias" });
  await expect(listado.locator("details")).toHaveCount(20);
  // El canal de novedades puede refrescar la página inicial al conectarse.
  expect([...new Set(offsets)]).toEqual([0]);
  expect(await listado.evaluate((elemento) => elemento.scrollHeight > elemento.clientHeight)).toBe(true);
  await listado.evaluate((elemento) => { elemento.scrollTop = elemento.scrollHeight; });
  await expect(listado.locator("details")).toHaveCount(40);
  await listado.evaluate((elemento) => { elemento.scrollTop = elemento.scrollHeight; });
  await expect(listado.locator("details")).toHaveCount(45);
  await expect(listado.getByRole("button", { name: "Cargar más" })).toHaveCount(0);
  expect([...new Set(offsets)]).toEqual([0, 20, 40]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
