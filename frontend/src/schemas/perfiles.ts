import { z } from "zod";

const cantidad = z.string().regex(/^\d+(\.\d{1,3})?$/);
export const perfilCompetenciaSchema = z.object({
  ongId: z.uuid(),
  nombre: z.string(),
  estadoOng: z.enum(["PENDIENTE", "HABILITADA", "SUSPENDIDA", "BAJA"]),
  evaluadoEn: z.iso.datetime({ offset: true }),
  capacidadesDeclaradas: z.array(z.object({
    capacidadId: z.uuid(), codigo: z.string(), nombre: z.string(),
    tipo: z.enum(["PERSONAL", "VEHICULO", "EQUIPAMIENTO", "SUMINISTRO"]),
    unidad: z.string(), admiteFracciones: z.boolean(),
    cantidadTotal: cantidad, cantidadComprometida: cantidad, cantidadDisponible: cantidad,
  })),
});
export type PerfilCompetencia = z.infer<typeof perfilCompetenciaSchema>;
