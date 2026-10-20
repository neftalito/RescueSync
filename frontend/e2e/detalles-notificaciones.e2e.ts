import { expect, test } from "@playwright/test";

import { casosDetalle } from "../src/test/fixtures/detallesNotificacion";

for (const caso of casosDetalle) {
  test(`el ojo abre ${caso.nombre} del aviso`, async ({ page }) => {
    const mutaciones: string[] = [];
    const aviso = {
      id: caso.id, usuario_id: 7, tipo: caso.tipo, titulo: caso.titulo,
      mensaje: "Novedad de la emergencia en Ribera norte: Inundación con familias evacuadas",
      ruta: `/notificaciones/${caso.id}`, leida_en: null as string | null,
      creada_en: "2026-10-19T10:00:00Z",
    };
    await page.routeWebSocket("**/notificaciones/ws", () => undefined);
    await page.route("**/api/v1/**", async route => {
      const solicitud = route.request();
      const ruta = new URL(solicitud.url()).pathname;
      if (solicitud.method() !== "GET") mutaciones.push(`${solicitud.method()} ${ruta}`);
      if (ruta.endsWith("/auth/me")) {
        await route.fulfill({ json: {
          usuario: { id: 7, email: "usuario@prueba.org", rol: caso.rol, requiere_cambio_password: false,
            organizacion: caso.rol === "AUDITOR_DIRECTIVO" ? null : {
              id: 3, nombre: "Organización", tipo: caso.rol === "REPRESENTANTE_ONG" ? "ONG" : "CENTRO_COORDINADOR",
            } }, csrf_token: "csrf-e2e",
        } });
      } else if (ruta.endsWith(`/notificaciones/${caso.id}/detalle`)) {
        await route.fulfill({ json: caso.detalle });
      } else if (ruta.endsWith(`/notificaciones/${caso.id}/leida`)) {
        expect(solicitud.headers()["x-csrf-token"]).toBe("csrf-e2e");
        aviso.leida_en = "2026-10-19T10:01:00Z";
        await route.fulfill({ json: aviso });
      } else if (ruta.endsWith("/notificaciones")) {
        await route.fulfill({ json: [aviso] });
      } else {
        await route.fulfill({ json: [] });
      }
    });

    await page.goto("/");
    await page.getByRole("button", { name: "Notificaciones", exact: true }).click();
    const panel = page.getByRole("region", { name: "Notificaciones", exact: true });
    await expect(panel.getByText(caso.titulo, { exact: true })).toBeVisible();
    await panel.getByRole("link", { name: "Ver detalle" }).click();

    await expect(page).toHaveURL(new RegExp(`/notificaciones/${caso.id}$`));
    await expect(panel).toBeHidden();
    await expect(page.getByRole("heading", { name: "Ribera norte" })).toBeVisible();
    if (caso.detalle.clase === "OFERTA_RECIBIDA" || (caso.detalle.clase === "CONVOCATORIA" && caso.detalle.mi_oferta)) {
      await expect(page.getByText("Bidones de agua", { exact: true })).toBeVisible();
      await expect(page.getByText(/Ayuda del Delta/)).toBeVisible();
    } else if (caso.detalle.clase === "TAREA_BONITA_FALLIDA") {
      await expect(page.getByRole("heading", { name: "Validar ofertas" })).toBeVisible();
      await expect(page.getByText("Estado al generar el aviso: Fallida")).toBeVisible();
    } else if (caso.detalle.clase === "CONVOCATORIA") {
      await expect(page.getByText(caso.detalle.convocatoria.estado === "ABIERTA"
        ? "Tu ONG todavía no presentó una oferta para esta convocatoria."
        : "Tu ONG no participó en esta convocatoria.", { exact: true })).toBeVisible();
    }
    if (caso.detalle.clase === "CONVOCATORIA") {
      await expect(page.getByRole("heading", { name: "Convocatoria N.º 1" })).toBeVisible();
      await expect(page.getByText("100,00 litros", { exact: true })).toBeVisible();
    }
    await expect.poll(() => mutaciones).toEqual([`PATCH /api/v1/notificaciones/${caso.id}/leida`]);
    await expect(page.getByRole("alert")).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
