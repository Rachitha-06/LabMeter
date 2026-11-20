import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Forecasts from "./Forecasts.jsx";
import { forecasts as forecastsApi, labs as labsApi, models as modelsApi } from "../api/endpoints.js";
import { ApiError } from "../api/client.js";
import { renderWithAuth } from "../test/renderWithAuth.jsx";

vi.mock("../components/Chart.jsx", () => ({
  default: ({ data }) => <div data-testid="chart">{data.length} traces</div>,
}));

vi.mock("../api/endpoints.js", () => ({
  labs: { list: vi.fn(), dataRange: vi.fn() },
  forecasts: { list: vi.fn(), get: vi.fn(), create: vi.fn(), evaluation: vi.fn() },
  models: { comparison: vi.fn(), status: vi.fn() },
}));

const LAB = { id: 2, name: "Electronics Lab", timezone: "Asia/Kolkata" };

const EVALUATION = {
  model: "comparable_day_mean v1",
  timezone: "Asia/Kolkata",
  lab_id: 2,
  lab_name: "Electronics Lab",
  split: {
    train: { start: "2026-07-06", end: "2026-08-10", days: 39 },
    validation: { start: "2026-08-11", end: "2026-08-18", days: 8 },
    test: { start: "2026-08-19", end: "2026-08-27", days: 9 },
  },
  validation_selection: [{ k: 4, mae: 0.5, rmse: 0.7, days_evaluated: 8, days_skipped_insufficient_history: 0 }],
  chosen_k: 4,
  test: { mae: 0.42, rmse: 0.61, hours_evaluated: 198, days_evaluated: 9, days_skipped_insufficient_history: 0, daily_total_mae: 3.1 },
  daily: [{ date: "2026-08-19", actual_kwh: 90.1, predicted_kwh: 91.4 }],
  notes: ["k was chosen on the validation period."],
};

const COMPARISON = {
  split: { test: { start: "2026-09-20", end: "2026-10-03" } },
  test: {
    baseline: { mae: 0.1374, rmse: 0.3052 },
    linear_regression: { mae: 0.2141, rmse: 0.332, vs_baseline: {
      mae: { metric: "MAE", difference: 0.0767, ci95: [0.0586, 0.0998], verdict: "less accurate than the baseline on MAE (95% interval excludes zero)" },
      rmse: { metric: "RMSE", difference: 0.0267, ci95: [-0.0357, 0.0919], verdict: "no clear difference from the baseline on RMSE (95% interval includes zero)" } } },
    random_forest: { mae: 0.1391, rmse: 0.2978, vs_baseline: {
      mae: { metric: "MAE", difference: 0.0017, ci95: [-0.0203, 0.0249], verdict: "no clear difference from the baseline on MAE (95% interval includes zero)" },
      rmse: { metric: "RMSE", difference: -0.0074, ci95: [-0.0661, 0.0501], verdict: "no clear difference from the baseline on RMSE (95% interval includes zero)" } } },
    days_compared: 14,
    hours_compared: 1004,
  },
  notes: ["Scores are per hour."],
};

beforeEach(() => {
  vi.clearAllMocks();
  labsApi.list.mockResolvedValue([LAB]);
  labsApi.dataRange.mockResolvedValue({ timezone: "Asia/Kolkata", first_day: "2026-07-06", last_day: "2026-10-03" });
  forecastsApi.list.mockResolvedValue([]);
  forecastsApi.evaluation.mockResolvedValue(EVALUATION);
  modelsApi.comparison.mockResolvedValue(COMPARISON);
});

async function chooseLab() {
  await screen.findByRole("option", { name: "Electronics Lab" });
  fireEvent.change(screen.getByLabelText(/laboratory/i), { target: { value: "2" } });
}

describe("Forecasts page", () => {
  it("shows the held-out accuracy and the chosen window after a lab is chosen", async () => {
    renderWithAuth(<Forecasts />, { permissions: ["forecasts:read", "forecasts:create"] });
    await chooseLab();
    expect(await screen.findByText("0.420 kWh")).toBeInTheDocument();
    expect(screen.getByText(/2026-08-19 to 2026-08-27/)).toBeInTheDocument();
    expect(forecastsApi.evaluation).toHaveBeenCalledWith("2");
  });

  it("explains a refusal when there is not enough history", async () => {
    forecastsApi.create.mockRejectedValue(
      new ApiError(422, "insufficient_history", "only 0 earlier Tuesdays are available; 2 are required",
        { comparable_days_found: 0, required: 2 }),
    );
    renderWithAuth(<Forecasts />, { permissions: ["forecasts:read", "forecasts:create"] });
    await chooseLab();
    fireEvent.click(await screen.findByRole("button", { name: /generate forecast/i }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("only 0 earlier Tuesdays are available");
    expect(alert).toHaveTextContent("insufficient_history");
  });

  it("shows the saved forecast with its estimated total and hourly chart", async () => {
    forecastsApi.create.mockResolvedValue({
      id: 9, predicted_kwh: "94.2000", horizon_start: "2026-08-10T00:00:00Z",
      details: { target_date: "2026-08-10", hourly_kwh: Array(24).fill(3.9), comparable_days: ["2026-08-03"] },
    });
    renderWithAuth(<Forecasts />, { permissions: ["forecasts:read", "forecasts:create"] });
    await chooseLab();
    fireEvent.click(await screen.findByRole("button", { name: /generate forecast/i }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved forecast 9");
    expect(screen.getByText(/2026-08-03/)).toBeInTheDocument();
    expect(screen.getAllByTestId("chart").length).toBeGreaterThanOrEqual(1);
  });

  it("disables forecast generation for a role without create permission", async () => {
    renderWithAuth(<Forecasts />, { permissions: ["forecasts:read"] });
    await chooseLab();
    expect(await screen.findByRole("button", { name: /generate forecast/i })).toBeDisabled();
  });

  it("reports an evaluation that cannot be produced", async () => {
    forecastsApi.evaluation.mockRejectedValue(new ApiError(422, "insufficient_history", "need at least 28 days of data for evaluation, found 3"));
    renderWithAuth(<Forecasts />, { permissions: ["forecasts:read"] });
    await chooseLab();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("need at least 28 days"));
  });

  it("reports the models' test-period verdicts without claiming a win the data does not support", async () => {
    renderWithAuth(<Forecasts />, { permissions: ["forecasts:read"] });
    await chooseLab();
    expect(await screen.findByText(/no clear difference from the baseline on MAE/i)).toBeInTheDocument();
    expect(screen.getByText(/less accurate than the baseline on MAE/i)).toBeInTheDocument();
    expect(screen.queryByText(/more accurate than the baseline/i)).not.toBeInTheDocument();
  });

  it("explains that models are unavailable until they are trained", async () => {
    modelsApi.comparison.mockRejectedValue(new ApiError(404, "not_trained", "no evaluation report found; run scripts/ml/train_models.py first"));
    renderWithAuth(<Forecasts />, { permissions: ["forecasts:read"] });
    await chooseLab();
    expect(await screen.findByText(/run scripts\/ml\/train_models\.py/)).toBeInTheDocument();
  });

  it("sends the chosen model with the forecast request", async () => {
    forecastsApi.create.mockResolvedValue({ id: 3, predicted_kwh: "90.0", horizon_start: "2026-08-24T00:00:00Z",
      model_name: "random_forest", details: { target_date: "2026-08-24", hourly_kwh: Array(24).fill(3.75) } });
    renderWithAuth(<Forecasts />, { permissions: ["forecasts:read", "forecasts:create"] });
    await chooseLab();
    fireEvent.change(screen.getByLabelText(/^model$/i), { target: { value: "random_forest" } });
    fireEvent.click(await screen.findByRole("button", { name: /generate forecast/i }));
    await waitFor(() => expect(forecastsApi.create).toHaveBeenCalled());
    const body = forecastsApi.create.mock.calls[0][0];
    expect(body.model).toBe("random_forest");
    expect(body.comparable_days).toBeUndefined();
  });

  it("explains a refusal for a day inside the model's training period", async () => {
    forecastsApi.create.mockRejectedValue(new ApiError(422, "outside_training_window",
      "2026-08-10 is inside the period this model was trained on (up to 2026-08-21). Choose a later day, or use the baseline."));
    renderWithAuth(<Forecasts />, { permissions: ["forecasts:read", "forecasts:create"] });
    await chooseLab();
    fireEvent.change(screen.getByLabelText(/^model$/i), { target: { value: "random_forest" } });
    fireEvent.click(await screen.findByRole("button", { name: /generate forecast/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("inside the period this model was trained on");
  });
});
