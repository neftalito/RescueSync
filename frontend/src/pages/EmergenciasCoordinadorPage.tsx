import type { ReactElement } from "react";
import { Link, useSearchParams } from "react-router";

import { ActionIcon } from "../components/ActionIcon";
import { BandejaEmergencias } from "../components/BandejaEmergencias";
import { estados, estadoLabels } from "../schemas/emergencia";

interface EmergenciasCoordinadorPageProps {
  vista: "pendientes" | "con-lotes";
}

export function EmergenciasCoordinadorPage({
  vista,
}: EmergenciasCoordinadorPageProps): ReactElement {
  const [searchParams, setSearchParams] = useSearchParams();
  const conLotes = vista === "con-lotes";
  const estado = conLotes
    ? estados.find((valor) => valor === searchParams.get("estado"))
    : undefined;

  return (
    <main className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div>
            <p className="text-sm font-black tracking-[0.16em] text-cyan-700 uppercase">
              RescueSync
            </p>
            <h1 className="mt-1 text-xl font-bold text-slate-950">
              {conLotes ? "Emergencias no pendientes" : "Emergencias pendientes"}
            </h1>
          </div>
          <Link
            to="/"
            className="action-button action-icon"
            title="Volver al inicio"
          >
            <ActionIcon name="home" />
            <span className="sr-only">Volver al inicio</span>
          </Link>
        </div>
      </header>
      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-6">
        <p className="mb-6 text-slate-600">
          {conLotes
            ? "Emergencias con lotes ya creados, incluidos los borradores."
            : "Emergencias disponibles para tu centro que todavía no tienen lotes."}
        </p>
        {conLotes && (
          <div className="mb-6 max-w-sm">
            <label
              htmlFor="estado-emergencia"
              className="text-sm font-semibold text-slate-700"
            >
              Estado de la emergencia
            </label>
            <select
              id="estado-emergencia"
              className="form-input mt-2"
              value={estado ?? ""}
              onChange={(event) => {
                setSearchParams((actuales) => {
                  const siguientes = new URLSearchParams(actuales);
                  if (event.target.value) {
                    siguientes.set("estado", event.target.value);
                  } else {
                    siguientes.delete("estado");
                  }
                  return siguientes;
                });
              }}
            >
              <option value="">Todos los estados</option>
              {estados.map((valor) => (
                <option key={valor} value={valor}>
                  {estadoLabels[valor]}
                </option>
              ))}
            </select>
          </div>
        )}
        <BandejaEmergencias
          rol="COORDINADOR_REGIONAL"
          vista={vista}
          estado={estado}
        />
      </div>
    </main>
  );
}
