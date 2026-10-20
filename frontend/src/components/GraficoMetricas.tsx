import { ListadoLocal } from "./ListadoProgresivo";
import type { ReactElement } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface Punto {
  nombre: string;
  valor: number;
  color?: string;
}
interface Props {
  titulo: string;
  datos: Punto[];
  tipo?: "barras" | "lineas" | "torta";
  unidad?: string;
}
const colores = [
  "#0e7490",
  "#0f766e",
  "#6366f1",
  "#b45309",
  "#be123c",
  "#64748b",
  "#475569",
];

export function GraficoMetricas({
  titulo,
  datos,
  tipo = "barras",
  unidad = "Cantidad",
}: Props): ReactElement {
  return (
    <article
      data-reporte-grafico={titulo}
      className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6"
    >
      <h3 className="text-lg font-bold text-slate-900">{titulo}</h3>
      {datos.some((d) => d.valor > 0) ? (
        <div
          className="mt-5 h-72 min-w-0"
          role="group"
          aria-label={`${titulo}. Datos disponibles en la tabla siguiente.`}
        >
          <ResponsiveContainer
            width="100%"
            height="100%"
            initialDimension={{ width: 500, height: 288 }}
          >
            {tipo === "torta" ? (
              <PieChart accessibilityLayer>
                <Pie
                  data={datos.filter((d) => d.valor > 0)}
                  dataKey="valor"
                  nameKey="nombre"
                  innerRadius="48%"
                  outerRadius="72%"
                  isAnimationActive={false}
                >
                  {datos
                    .filter((d) => d.valor > 0)
                    .map((d, i) => (
                      <Cell
                        key={d.nombre}
                        fill={d.color ?? colores[i % colores.length]}
                      />
                    ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            ) : tipo === "lineas" ? (
              <LineChart
                data={datos}
                accessibilityLayer
                margin={{ left: 0, right: 20, top: 10, bottom: 25 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="nombre" tick={{ fontSize: 11 }} />
                <YAxis
                  allowDecimals={false}
                  width={35}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="valor"
                  name={unidad}
                  stroke="#0e7490"
                  strokeWidth={3}
                  isAnimationActive={false}
                />
                <Legend />
              </LineChart>
            ) : (
              <BarChart
                data={datos}
                accessibilityLayer
                margin={{ left: 0, right: 15, top: 10, bottom: 45 }}
              >
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis
                  dataKey="nombre"
                  tick={{ fontSize: 10 }}
                  angle={-20}
                  textAnchor="end"
                  interval={0}
                  height={65}
                />
                <YAxis
                  width={38}
                  tick={{ fontSize: 11 }}
                  allowDecimals={unidad !== "Cantidad"}
                />
                <Tooltip />
                <Legend />
                <Bar
                  dataKey="valor"
                  name={unidad}
                  fill="#0e7490"
                  radius={[5, 5, 0, 0]}
                  isAnimationActive={false}
                >
                  {datos.map((d) => (
                    <Cell key={d.nombre} fill={d.color ?? "#0e7490"} />
                  ))}
                </Bar>
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="mt-6 text-sm text-slate-500">
          Sin datos para graficar con estos filtros.
        </p>
      )}
      <details className="mt-4 text-sm text-slate-600">
        <summary className="cursor-pointer font-semibold text-cyan-800">
          Ver datos de {titulo.toLowerCase()}
        </summary>
        <ListadoLocal items={datos} etiqueta={`Datos de ${titulo.toLowerCase()}`} className="mt-3">
          {(visibles) => (
            <table className="w-full text-left">
              <caption className="sr-only">{titulo}</caption>
              <thead className="sticky top-0 bg-white">
                <tr>
                  <th className="py-2">Categoría</th>
                  <th className="py-2 text-right">{unidad}</th>
                </tr>
              </thead>
              <tbody>
                {visibles.map((d) => (
                  <tr key={d.nombre} className="border-t border-slate-100">
                    <td className="py-2 break-words">
                      {d.color && (
                        <span
                          aria-hidden="true"
                          className="mr-2 inline-block size-2 rounded-full"
                          style={{ backgroundColor: d.color }}
                        />
                      )}
                      {d.nombre}
                    </td>
                    <td className="py-2 text-right">
                      {d.valor.toLocaleString("es-AR", {
                        maximumFractionDigits: 2,
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </ListadoLocal>
      </details>
    </article>
  );
}
