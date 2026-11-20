import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Alerts from "./Alerts.jsx";
import { alerts as alertsApi, labs as labsApi } from "../api/endpoints.js";
import { renderWithAuth } from "../test/renderWithAuth.jsx";

vi.mock("../api/endpoints.js", () => ({
  labs: { list: vi.fn() },
  alerts: { list: vi.fn(), get: vi.fn(), detect: vi.fn(), update: vi.fn(), comment: vi.fn(), count: vi.fn() },
}));

const ALERT = {
  id: 7, lab_id: 2, lab_name: "Electronics Lab", period_local: "Mon 13 Jul 2026, 17:00–20:00 (Asia/Kolkata)",
  actual_kwh: "9.9000", expected_kwh: "1.6000", difference_kwh: "8.3000", severity: "high", status: "open",
  explanation: "Electronics Lab used 9.90 kWh. This is a suspected excess for review, not a confirmed waste.",
  reviews: [],
};

const DETAIL = { ...ALERT, reviews: [{ id: 1, from_status: "open", to_status: "under_review", comment: "checking" }] };

beforeEach(() => {
  vi.clearAllMocks();
  labsApi.list.mockResolvedValue([{ id: 2, name: "Electronics Lab" }]);
  alertsApi.list.mockResolvedValue([ALERT]);
  alertsApi.count.mockResolvedValue({ total: 1 });
  alertsApi.get.mockResolvedValue(DETAIL);
  alertsApi.detect.mockResolvedValue({
    created: 3, already_recorded: 0, labs: 3, labs_without_schedule: 0, days_evaluated: 79,
    days_skipped_exam: 10, days_skipped_holiday: 0, hours_without_history: 200, hours_without_reading: 0,
  });
});

describe("Alerts page", () => {
  it("lists alerts with their priority and status and explains that they are suspicions", async () => {
    renderWithAuth(<Alerts />, { permissions: ["alerts:read"] });
    expect(await screen.findByRole("row", { name: /Electronics Lab/ })).toBeInTheDocument();
    expect(screen.getByText(/none of them is a finding of waste/i)).toBeInTheDocument();
    expect(screen.getByText("Showing 1–1 of 1 alerts")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
  });

  it("reports a screening run with what was skipped and why", async () => {
    renderWithAuth(<Alerts />, { permissions: ["alerts:read", "alerts:detect"] });
    fireEvent.click(await screen.findByRole("button", { name: /run screening/i }));
    expect(await screen.findByRole("status")).toHaveTextContent("3 new alerts, 0 already recorded");
    expect(screen.getByRole("status")).toHaveTextContent("exam-period days skipped 10");
  });

  it("hides the screening button from roles that cannot run it", async () => {
    renderWithAuth(<Alerts />, { permissions: ["alerts:read"] });
    await screen.findByRole("row", { name: /Electronics Lab/ });
    expect(screen.queryByRole("button", { name: /run screening/i })).not.toBeInTheDocument();
  });

  it("requires a note before an alert can be resolved", async () => {
    alertsApi.update.mockResolvedValue({ ...DETAIL, status: "resolved" });
    renderWithAuth(<Alerts />, { permissions: ["alerts:read", "alerts:review"] });
    fireEvent.click(await screen.findByRole("button", { name: ALERT.period_local }));
    const resolve = await screen.findByRole("button", { name: /^resolve$/i });
    expect(resolve).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/review note/i), { target: { value: "equipment was left on" } });
    expect(resolve).toBeEnabled();
    fireEvent.click(resolve);
    await waitFor(() => expect(alertsApi.update).toHaveBeenCalledWith(7, {
      status: "resolved", comment: "equipment was left on" }));
  });

  it("shows evaluators the alert but none of the review actions", async () => {
    renderWithAuth(<Alerts />, { permissions: ["alerts:read"] });
    fireEvent.click(await screen.findByRole("button", { name: ALERT.period_local }));
    expect(await screen.findByText(/not a confirmed waste/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^resolve$/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/review note/i)).not.toBeInTheDocument();
  });
});
