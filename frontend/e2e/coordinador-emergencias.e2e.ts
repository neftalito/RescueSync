import { expect, test } from "@playwright/test";

const base = {
  municipio_id: 1, centro_coordinador_id: 3, creada_por_usuario_id: 1,
  gravedad: "ALTA", descripcion: "Familias evacuadas.",
  bonita_sync: "VINCULADA", bonita_process_instance_id: 1001,
  creada_en: "2026-09-19T18:20:39.102766Z", actualizada_en: "2026-09-19T18:20:39.102766Z",
};

test("separa las tarjetas y permite filtrar las emergencias con lotes conservando la URL", async ({
  page,
}, testInfo) => {
  let consultas = 0;
  await page.routeWebSocket("**/notificaciones/ws", () => undefined);
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/auth/me")) {
      await route.fulfill({ json: {
        usuario: {
          id: 2, email: "coordinador@rescuesync.org", rol: "COORDINADOR_REGIONAL",
          organizacion: { id: 3, nombre: "Centro Norte", tipo: "CENTRO_COORDINADOR" },
          requiere_cambio_password: false,
        },
        csrf_token: "csrf-e2e",
      } });
    } else if (path.endsWith("/notificaciones")) {
      await route.fulfill({ json: [] });
    } else if (path.endsWith("/emergencias")) {
      consultas++;
      await route.fulfill({ json: [
        { ...base, id: 31, zona: "Pendiente sin lotes", estado: "REGISTRADA", tiene_lotes: false },
        { ...base, id: 32, zona: "Con borradores", estado: "REGISTRADA", tiene_lotes: true },
        { ...base, id: 33, zona: "Convocatoria publicada", estado: "PUBLICADA", tiene_lotes: true },
        { ...base, id: 34, zona: "Respuesta finalizada", estado: "RESUELTA", tiene_lotes: true },
      ] });
    } else {
      await route.fulfill({ status: 404, json: { detail: "Ruta no simulada." } });
    }
  });
  await page.goto("/");
  const pendientes = page.getByRole("link", { name: "Ver emergencias pendientes" });
  await expect(pendientes).toBeVisible();
  await expect(page.getByRole("link", { name: "Ver emergencias no pendientes" })).toBeVisible();
  expect(consultas).toBe(0);
  await page.screenshot({ path: testInfo.outputPath("coordinador-inicio.png"), fullPage: true });

  await pendientes.click();
  await expect(page.getByText("Alta · Pendiente sin lotes")).toBeVisible();
  await expect(page.getByText("Alta · Con borradores")).toHaveCount(0);
  await expect(page.getByRole("combobox")).toHaveCount(0);
  await page.getByRole("link", { name: "Volver al inicio" }).click();
  await page.getByRole("link", { name: "Ver emergencias no pendientes" }).click();
  await expect(page.getByText("Alta · Con borradores")).toBeVisible();
  await expect(page.getByText("Alta · Convocatoria publicada")).toBeVisible();
  await expect(page.getByText("Alta · Pendiente sin lotes")).toHaveCount(0);
  const filtro = page.getByRole("combobox", { name: "Estado de la emergencia" });
  await filtro.selectOption("REGISTRADA");
  await expect(page.getByText("Alta · Con borradores")).toBeVisible();
  await expect(page.getByText("Alta · Convocatoria publicada")).toHaveCount(0);
  await expect(page).toHaveURL(/estado=REGISTRADA/);
  await filtro.selectOption("RESUELTA");
  await expect(page.getByText("Alta · Respuesta finalizada")).toBeVisible();
  await page.reload();
  await expect(filtro).toHaveValue("RESUELTA");
  await expect(page.getByText("Alta · Respuesta finalizada")).toBeVisible();
  await filtro.selectOption("EN_EVALUACION");
  await expect(page.getByRole("status")).toHaveText("No hay emergencias con lotes en el estado seleccionado.");
  await filtro.selectOption("");
  await expect(page.getByText("Alta · Con borradores")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("coordinador-con-lotes.png"), fullPage: true });
});
