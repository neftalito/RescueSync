import { estadoOfertaLabels, type Oferta } from "../schemas/oferta";

/** Explica las restricciones de edición que informa la API para la oferta. */
export function motivoOfertaNoEditable(oferta: Oferta): string | undefined {
  if (oferta.editable) return undefined;

  if (!["BORRADOR", "PRESENTADA"].includes(oferta.estado)) {
    return `La oferta está ${estadoOfertaLabels[oferta.estado].toLocaleLowerCase("es-AR")} y ya no admite modificaciones.`;
  }

  if ((oferta.participantes?.length ?? 0) > 1 && oferta.consorcio_editable) {
    return "Para modificar tus aportes, desarmá el consorcio, editá las ofertas individuales y creá una nueva propuesta con las confirmaciones de todas las ONGs.";
  }

  return "La convocatoria debe estar abierta y dentro del plazo permitido para modificar la oferta o el consorcio.";
}
