import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import App from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("muestra el flujo inicial y confirma que la API está disponible", async () => {
  const fetchMock = vi
    .fn<typeof fetch>()
    .mockResolvedValue(Response.json({ status: "ok" }));
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);

  expect(
    screen.getByRole("heading", {
      name: "Flujo inicial de atención de emergencias",
    }),
  ).toBeInTheDocument();
  expect(await screen.findByText("API disponible")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledOnce();
});
