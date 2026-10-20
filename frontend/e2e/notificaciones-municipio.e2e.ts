import { expect, test } from "@playwright/test";

for (const titulo of ["Emergencia publicada", "Emergencia en evaluación"]) {
  test(`${titulo}: el ojo abre la ejecución de la emergencia del aviso`, async ({ page }) => {
    const notificacion = {
      id: 41,
      usuario_id: 7,
      tipo: "EMERGENCIA_ESTADO_ACTUALIZADO",
      titulo,
      mensaje: titulo === "Emergencia publicada"
        ? "El centro coordinador publicó la convocatoria de la emergencia en Ribera norte: Inundación con familias evacuadas"
        : "Cerró la convocatoria y las ofertas están siendo evaluadas. Emergencia en Ribera norte: Inundación con familias evacuadas",
      ruta: "/emergencias/31/ejecucion",
      creada_en: "2026-10-20T10:00:00Z",
      leida_en: null as string | null,
    };
    let marcadaComoLeida = false;
    await page.routeWebSocket("**/notificaciones/ws", () => undefined);
    await page.route("**/api/v1/**", async (route) => {
      const ruta = new URL(route.request().url()).pathname;
      if (ruta.endsWith("/auth/me")) {
        await route.fulfill({ json: {
          usuario: {
            id: 7,
            email: "municipio@prueba.org",
            rol: "OPERADOR_MUNICIPAL",
            organizacion: { id: 1, nombre: "Municipio", tipo: "MUNICIPIO" },
            requiere_cambio_password: false,
          },
          csrf_token: "csrf-e2e",
        } });
      } else if (ruta.endsWith("/notificaciones/41/leida")) {
        expect(route.request().method()).toBe("PATCH");
        expect(route.request().headers()["x-csrf-token"]).toBe("csrf-e2e");
        marcadaComoLeida = true;
        notificacion.leida_en = "2026-10-20T10:01:00Z";
        await route.fulfill({ json: notificacion });
      } else if (ruta.endsWith("/notificaciones")) {
        await route.fulfill({ json: [notificacion] });
      } else if (ruta.endsWith("/emergencias/31/adjudicaciones")) {
        await route.fulfill({ json: {
          idEmergencia: 31,
          estado: titulo === "Emergencia publicada" ? "PUBLICADA" : "EN_EVALUACION",
          puedeSolicitarCierre: false,
          adjudicaciones: [],
          cierre: null,
        } });
      } else if (ruta.endsWith("/emergencias/31/ofertas-validadas")) {
        await route.fulfill({ json: {
          validacion: null, permiteParcial: false, aportes: [], diagnosticos: [],
        } });
      } else {
        await route.fulfill({ json: [] });
      }
    });

    await page.goto("/");
    await page.getByRole("button", { name: "Notificaciones", exact: true }).click();
    const panel = page.getByRole("region", { name: "Notificaciones", exact: true });
    await expect(panel.getByText(titulo, { exact: true })).toBeVisible();
    await expect(panel.getByText(notificacion.mensaje, { exact: true })).toBeVisible();
    const detalle = panel.getByRole("link", { name: "Ver detalle" });
    await expect(detalle).toHaveAttribute("href", "/emergencias/31/ejecucion");
    await detalle.click();

    await expect(page).toHaveURL(/\/emergencias\/31\/ejecucion$/);
    await expect(panel).toBeHidden();
    await expect(page.getByRole("heading", {
      name: "Evaluación y ejecución de emergencia #31",
    })).toBeVisible();
    await expect.poll(() => marcadaComoLeida).toBe(true);
    await expect(page.getByRole("alert")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
