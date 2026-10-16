from decimal import Decimal
from itertools import product
from random import Random
from uuid import UUID

from app.schemas.ejecucion import AporteElegible
from app.services.cobertura_validada import Requerimiento, calcular_cobertura


def aporte(
    identidad: int, recurso: int, lote: int, disponible: int, cantidad: str = "6"
) -> AporteElegible:
    return AporteElegible(
        aporte_id=identidad,
        oferta_id=identidad,
        version=1,
        lote_id=lote,
        ong_id=1,
        ong_nacional_id=UUID(int=1),
        recurso_nacional_id=UUID(int=recurso),
        capacidad_nacional_id=UUID(int=9),
        riesgo_requerido="ALTA",
        cantidad_ofrecida=Decimal(cantidad),
        cantidad_disponible=Decimal(disponible),
        unidad="personas",
        admite_fracciones=False,
        clasificacion="PRINCIPAL",
    )


def test_un_recurso_no_cubre_dos_veces_su_disponibilidad() -> None:
    cobertura = calcular_cobertura(
        [
            Requerimiento(1, Decimal(6), "personas"),
            Requerimiento(2, Decimal(6), "personas"),
        ],
        [aporte(1, 1, 1, 10), aporte(2, 1, 2, 10)],
    )
    assert sum(l.cantidad_asignable for l in cobertura) == 10
    assert sum(l.faltante for l in cobertura) == 2


def test_flujo_residual_corrige_una_asignacion_greedy() -> None:
    lotes = [
        Requerimiento(1, Decimal(6), "personas"),
        Requerimiento(2, Decimal(6), "personas"),
    ]
    aportes = [aporte(1, 1, 1, 6), aporte(2, 1, 2, 6), aporte(3, 2, 1, 6)]
    resultado = calcular_cobertura(lotes, aportes)
    assert all(l.faltante == 0 for l in resultado)
    assert resultado[0].aportes[0].aporte_id == 3
    assert (
        calcular_cobertura(list(reversed(lotes)), list(reversed(aportes))) == resultado
    )


def test_fracciones_exactas_y_cero_disponibilidad() -> None:
    a = aporte(1, 1, 1, 0, "0.125").model_copy(
        update={"admite_fracciones": True, "cantidad_disponible": Decimal("0.125")}
    )
    resultado = calcular_cobertura([Requerimiento(1, Decimal("0.250"), "litros")], [a])
    assert resultado[0].cantidad_asignable == Decimal("0.125") and resultado[
        0
    ].faltante == Decimal("0.125")
    assert (
        calcular_cobertura(
            [Requerimiento(1, Decimal(2), "personas")], [aporte(1, 1, 1, 0)]
        )[0].cantidad_asignable
        == 0
    )


def test_cobertura_coincide_con_busqueda_exhaustiva_en_redes_pequenas() -> None:
    generador = Random(36)
    for _ in range(40):
        disponibilidad = {rid: generador.randint(0, 3) for rid in range(1, 4)}
        requeridas = {lid: generador.randint(1, 3) for lid in range(1, 4)}
        aportes = [
            aporte(aid, generador.randint(1, 3), generador.randint(1, 3), 0, "1")
            for aid in range(1, 8)
        ]
        for a in aportes:
            a.cantidad_disponible = Decimal(disponibilidad[a.recurso_nacional_id.int])
        maximo = 0
        for cantidades in product((0, 1), repeat=len(aportes)):
            if all(
                sum(
                    c
                    for c, a in zip(cantidades, aportes, strict=True)
                    if a.recurso_nacional_id.int == rid
                )
                <= capacidad
                for rid, capacidad in disponibilidad.items()
            ) and all(
                sum(
                    c
                    for c, a in zip(cantidades, aportes, strict=True)
                    if a.lote_id == lid
                )
                <= cantidad
                for lid, cantidad in requeridas.items()
            ):
                maximo = max(maximo, sum(cantidades))
        resultado = calcular_cobertura(
            [
                Requerimiento(lid, Decimal(cantidad), "personas")
                for lid, cantidad in requeridas.items()
            ],
            aportes,
        )
        assert sum(l.cantidad_asignable for l in resultado) == maximo
