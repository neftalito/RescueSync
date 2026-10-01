import { describe, expect, it } from "vitest";

import {
  formatearCantidad,
  formatearCantidadParaFormulario,
} from "./cantidades";

describe("formatearCantidad", () => {
  it("muestra coma decimal, separadores de miles y dos decimales", () => {
    expect(formatearCantidad("1.000")).toBe("1,00");
    expect(formatearCantidad("1000.000")).toBe("1.000,00");
    expect(formatearCantidad("12345.678")).toBe("12.345,68");
  });

  it("omite separadores de miles al preparar un valor editable", () => {
    expect(formatearCantidadParaFormulario("1.000")).toBe("1,00");
    expect(formatearCantidadParaFormulario("1000.000")).toBe("1000,00");
  });
});
