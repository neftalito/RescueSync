"""Calcula una asignación global factible, sin reservar ni duplicar disponibilidad."""

from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.schemas.ejecucion import (
    AporteElegible,
    Asignacion,
    CoberturaLote,
)


@dataclass(frozen=True)
class Requerimiento:
    lote_id: int
    cantidad: Decimal
    unidad: str


def calcular_cobertura(
    lotes: list[Requerimiento],
    aportes: list[AporteElegible],
) -> list[CoberturaLote]:
    """Usa flujo máximo entero en milésimas con caminos residuales.

    Una componente comparte capacidad y unidad. Si es discreta todos sus límites
    se expresan en enteros; la integridad del flujo conserva esa granularidad.
    El orden de construcción hace determinista la propuesta.
    """
    red: dict[str, dict[str, int]] = {}

    def arista(origen: str, destino: str, capacidad: int) -> None:
        red.setdefault(origen, {})[destino] = capacidad
        red.setdefault(destino, {}).setdefault(origen, 0)

    recursos: dict[UUID, AporteElegible] = {}
    for a in sorted(aportes, key=lambda a: a.aporte_id):
        recursos.setdefault(a.recurso_nacional_id, a)
    for rid, a in sorted(recursos.items()):
        # Las disponibilidades discretas se redondean hacia abajo, nunca hacia arriba.
        disponible = a.cantidad_disponible
        if not a.admite_fracciones:
            disponible = disponible.to_integral_value(rounding="ROUND_FLOOR")
        arista("S", f"R{rid}", int(disponible * 1000))
    for a in sorted(aportes, key=lambda a: a.aporte_id):
        arista(
            f"R{a.recurso_nacional_id}",
            f"A{a.aporte_id}",
            int(a.cantidad_ofrecida * 1000),
        )
        arista(f"A{a.aporte_id}", f"L{a.lote_id}", int(a.cantidad_ofrecida * 1000))
    for lote in sorted(lotes, key=lambda l: l.lote_id):
        arista(f"L{lote.lote_id}", "T", int(lote.cantidad * 1000))

    vecinos = {nodo: list(aristas) for nodo, aristas in red.items()}
    while True:
        niveles = {"S": 0}
        pendientes = deque(["S"])
        while pendientes:
            nodo = pendientes.popleft()
            for vecino, capacidad in red.get(nodo, {}).items():
                if capacidad > 0 and vecino not in niveles:
                    niveles[vecino] = niveles[nodo] + 1
                    pendientes.append(vecino)
        if "T" not in niveles:
            break
        # Flujo bloqueante de Dinic. El recorrido iterativo evita desbordar la
        # pila cuando un camino residual conecta muchos lotes.
        posiciones = dict.fromkeys(red, 0)
        while True:
            camino: list[tuple[str, str]] = []
            nodo = "S"
            while nodo != "T":
                while posiciones[nodo] < len(vecinos[nodo]):
                    vecino = vecinos[nodo][posiciones[nodo]]
                    if (
                        red[nodo][vecino] > 0
                        and niveles.get(vecino) == niveles[nodo] + 1
                    ):
                        break
                    posiciones[nodo] += 1
                else:
                    if not camino:
                        break
                    nodo, _ = camino.pop()
                    posiciones[nodo] += 1
                    continue
                camino.append((nodo, vecino))
                nodo = vecino
            if nodo != "T":
                break
            flujo = min(red[origen][destino] for origen, destino in camino)
            for origen, destino in camino:
                red[origen][destino] -= flujo
                red[destino][origen] += flujo

    resultado: list[CoberturaLote] = []
    for lote in sorted(lotes, key=lambda l: l.lote_id):
        asignaciones = [
            Asignacion(
                aporte_id=a.aporte_id,
                cantidad=Decimal(red[f"L{lote.lote_id}"][f"A{a.aporte_id}"]) / 1000,
            )
            for a in sorted(aportes, key=lambda a: a.aporte_id)
            if a.lote_id == lote.lote_id
            and red[f"L{lote.lote_id}"][f"A{a.aporte_id}"] > 0
        ]
        asignado = sum((a.cantidad for a in asignaciones), Decimal(0))
        resultado.append(
            CoberturaLote(
                lote_id=lote.lote_id,
                cantidad_requerida=lote.cantidad,
                cantidad_asignable=asignado,
                faltante=lote.cantidad - asignado,
                unidad=lote.unidad,
                aportes=asignaciones,
            )
        )
    return resultado
