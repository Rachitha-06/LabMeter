import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Energy from "./Energy.jsx";
import { energy as energyApi } from "../api/endpoints.js";
import { ApiError } from "../api/client.js";
import { renderWithAuth } from "../test/renderWithAuth.jsx";

vi.mock("../api/endpoints.js", () => ({
  energy: { tariffs: vi.fn(), factors: vi.fn(), createTariff: vi.fn(), createFactor: vi.fn(), estimate: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
  energyApi.tariffs.mockResolvedValue([]);
  energyApi.factors.mockResolvedValue([]);
});

describe("Tariffs and factors page", () => {
  it("says plainly that no values ship with the system", async () => {
    renderWithAuth(<Energy />, { permissions: ["energy:read", "energy:write"] });
    expect(await screen.findByText(/does not ship official values/i)).toBeInTheDocument();
    expect(screen.getByText(/stay hidden until at least one tariff band/i)).toBeInTheDocument();
  });

  it("sends no weekday restriction when every day is selected", async () => {
    energyApi.createTariff.mockResolvedValue({ id: 1 });
    renderWithAuth(<Energy />, { permissions: ["energy:read", "energy:write"] });
    fireEvent.change(await screen.findByLabelText(/^rate per kwh$/i), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText(/currency code/i), { target: { value: "inr" } });
    fireEvent.change(screen.getByLabelText(/source of this rate/i), { target: { value: "Tariff order, 1 April 2026" } });
    fireEvent.click(screen.getByRole("button", { name: /save tariff band/i }));
    await waitFor(() => expect(energyApi.createTariff).toHaveBeenCalled());
    const body = energyApi.createTariff.mock.calls[0][0];
    expect(body.weekdays).toBeNull();
    expect(body.currency).toBe("INR");
  });

  it("shows the overlap refusal from the server", async () => {
    energyApi.createTariff.mockRejectedValue(new ApiError(409, "tariff_overlap",
      "this band overlaps an existing one in date, weekday and hours"));
    renderWithAuth(<Energy />, { permissions: ["energy:read", "energy:write"] });
    fireEvent.change(await screen.findByLabelText(/^rate per kwh$/i), { target: { value: "12" } });
    fireEvent.change(screen.getByLabelText(/currency code/i), { target: { value: "INR" } });
    fireEvent.change(screen.getByLabelText(/source of this rate/i), { target: { value: "Tariff order, 1 April 2026" } });
    fireEvent.click(screen.getByRole("button", { name: /save tariff band/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("overlaps an existing one");
  });

  it("is read-only for roles that cannot change tariffs", async () => {
    energyApi.tariffs.mockResolvedValue([{ id: 1, rate_per_kwh: "12.0000", currency: "INR", effective_from: "2026-01-01",
      effective_to: null, time_band: "peak", start_hour: 9, end_hour: 17, weekdays: "0,1,2,3,4", source: "Tariff order" }]);
    renderWithAuth(<Energy />, { permissions: ["energy:read"] });
    expect(await screen.findByText("peak")).toBeInTheDocument();
    expect(screen.getByText(/read-only for your role/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save tariff band/i })).not.toBeInTheDocument();
  });
});
