import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EstimateCards from "./EstimateCards.jsx";
import { energy as energyApi } from "../api/endpoints.js";
import { ApiError } from "../api/client.js";

vi.mock("../api/endpoints.js", () => ({
  energy: { estimate: vi.fn() },
}));

const WITH_DATA = {
  currency: "INR", emission_unit: "kgCO2e/kWh",
  total: { estimated_cost: "42.00", kwh_with_tariff: "5.0000", kwh_without_tariff: "0.0000",
           estimated_emissions: "2.5000", kwh_without_factor: "0.0000" },
};

function renderCards(props = {}) {
  return render(<MemoryRouter><EstimateCards start="2026-10-03T00:00:00.000Z" end="2026-10-12T00:00:00.000Z" labId="" {...props} /></MemoryRouter>);
}

beforeEach(() => vi.clearAllMocks());

describe("EstimateCards", () => {
  it("shows the estimate with its label and the currency and unit it was made in", async () => {
    energyApi.estimate.mockResolvedValue(WITH_DATA);
    renderCards();
    expect(await screen.findByText("42.00 INR")).toBeInTheDocument();
    expect(screen.getByText("2.50 kgCO2e")).toBeInTheDocument();
    expect(screen.getByText(/not measured costs or emissions/i)).toBeInTheDocument();
  });

  it("explains how to proceed when no tariff is configured, without showing a number", async () => {
    energyApi.estimate.mockRejectedValue(new ApiError(422, "no_tariff",
      "no electricity tariff is configured. Add the tariff bands from your tariff order first."));
    renderCards();
    expect(await screen.findByText(/not estimated yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open tariffs and factors/i })).toHaveAttribute("href", "/energy");
    expect(screen.queryByText(/estimated cost/i)).not.toBeInTheDocument();
  });

  it("flags kWh that fall outside every tariff band instead of hiding them", async () => {
    energyApi.estimate.mockResolvedValue({ ...WITH_DATA, total: { ...WITH_DATA.total, kwh_without_tariff: "1.5000" } });
    renderCards();
    expect(await screen.findByText(/fall outside every configured tariff band/i)).toBeInTheDocument();
  });

  it("does not add up amounts across mixed currencies", async () => {
    energyApi.estimate.mockResolvedValue({ ...WITH_DATA, currency: null });
    renderCards();
    expect(await screen.findByText("Mixed currencies")).toBeInTheDocument();
  });
});
