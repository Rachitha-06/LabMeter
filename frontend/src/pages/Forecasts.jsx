import { useEffect, useState } from "react";
import Chart from "../components/Chart.jsx";
import { EmptyState, ErrorBanner, LoadingState, PageHeader, SuccessBanner } from "../components/States.jsx";
import { forecasts as forecastsApi, labs as labsApi, models as modelsApi } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { dayAfter, daysAgoInputValue, formatInZone, formatKwh, kwhNumber } from "../utils/format.js";

const HOURS = Array.from({ length: 24 }, (_, h) => `${String(h).padStart(2, "0")}:00`);

const MODEL_OPTIONS = [
  { value: "baseline", label: "Baseline (comparable days)" },
  { value: "linear_regression", label: "Linear regression" },
  { value: "random_forest", label: "Random forest" },
];
const MODEL_LABELS = Object.fromEntries(MODEL_OPTIONS.map((o) => [o.value, o.label]));

function tomorrowInputValue() {
  return daysAgoInputValue(-1);
}

function LabPicker({ labs, value, onChange }) {
  return (
    <div>
      <label className="label" htmlFor="fc-lab">Laboratory</label>
      <select id="fc-lab" className="input" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choose a laboratory</option>
        {labs.map((lab) => <option key={lab.id} value={lab.id}>{lab.name}</option>)}
      </select>
    </div>
  );
}

function GenerateForecast({ labId, canCreate, onCreated, initialDate }) {
  const [form, setForm] = useState({ target_date: initialDate, model: "baseline", comparable_days: 4, min_history: 2 });
  // Update only the date when the default changes, so the user's model and other choices are kept.
  useEffect(() => {
    setForm((current) => ({ ...current, target_date: initialDate }));
  }, [initialDate]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const body = { lab_id: Number(labId), target_date: form.target_date, model: form.model };
      if (form.model === "baseline") {
        body.comparable_days = Number(form.comparable_days);
        body.min_history = Number(form.min_history);
      }
      const created = await forecastsApi.create(body);
      setResult(created);
      onCreated();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const hourly = result?.details?.hourly_kwh ?? [];

  return (
    <section className="card space-y-4">
      <h2 className="text-sm font-semibold text-slate-700">Generate a baseline forecast</h2>
      <p className="text-xs text-slate-500">
        The estimate for each hour is the average of that hour on the most recent earlier days with the same weekday.
      </p>
      <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" onSubmit={submit}>
        <div>
          <label className="label" htmlFor="fc-day">Day to forecast</label>
          <input id="fc-day" type="date" className="input" required value={form.target_date}
            onChange={(e) => setForm({ ...form, target_date: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="fc-model">Model</label>
          <select id="fc-model" className="input" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}>
            {MODEL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </div>
        {form.model === "baseline" && (
          <>
            <div>
              <label className="label" htmlFor="fc-k">Comparable days (k)</label>
              <input id="fc-k" type="number" min={1} max={8} className="input" value={form.comparable_days}
                onChange={(e) => setForm({ ...form, comparable_days: e.target.value })} />
            </div>
            <div>
              <label className="label" htmlFor="fc-min">Minimum history</label>
              <input id="fc-min" type="number" min={1} max={8} className="input" value={form.min_history}
                onChange={(e) => setForm({ ...form, min_history: e.target.value })} />
            </div>
          </>
        )}
        <div className="flex items-end">
          <button type="submit" className="btn-primary w-full" disabled={!labId || busy || !canCreate}>
            {busy ? "Forecasting…" : "Generate forecast"}
          </button>
        </div>
      </form>
      <ErrorBanner error={error} />
      {result && (
        <div className="space-y-4">
          <SuccessBanner>
            Saved forecast {result.id} ({MODEL_LABELS[result.model_name] ?? result.model_name}): estimated total{" "}
            {formatKwh(result.predicted_kwh, 2)} for {result.details.target_date}.
          </SuccessBanner>
          {result.details.comparable_days && (
            <p className="text-sm text-slate-600">Based on {result.details.comparable_days.join(", ")}.</p>
          )}
          <Chart
            height={260}
            data={[{ type: "scatter", mode: "lines+markers", name: "Estimated kWh", x: HOURS, y: hourly,
              line: { color: "#047857" } }]}
            layout={{ xaxis: { title: "Hour (laboratory local time)" }, yaxis: { title: "kWh per hour" } }}
          />
        </div>
      )}
    </section>
  );
}

function ModelComparison() {
  const comparison = useAsync(() => modelsApi.comparison(), []);
  if (comparison.loading) return <LoadingState label="Loading model comparison…" />;
  if (comparison.error) {
    return (
      <section className="card">
        <h2 className="text-sm font-semibold text-slate-700">Model comparison</h2>
        <ErrorBanner error={comparison.error} />
      </section>
    );
  }
  const report = comparison.data;
  const test = report.test;
  const rows = [
    { key: "baseline", label: "Baseline (comparable days)", block: test.baseline, diff: null },
    { key: "linear_regression", label: "Linear regression", block: test.linear_regression, diff: test.linear_regression.vs_baseline },
    { key: "random_forest", label: "Random forest", block: test.random_forest, diff: test.random_forest.vs_baseline },
  ];
  return (
    <section className="card space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-slate-700">Model comparison on held-out days</h2>
        <p className="text-xs text-slate-500">
          All laboratories, test period {report.split.test.start} to {report.split.test.end} ({test.days_compared} days,
          {" "}{test.hours_compared} hours). Models were fitted before this period and never saw it.
        </p>
      </div>
      <table className="min-w-full text-sm">
        <thead><tr className="text-left text-xs uppercase text-slate-500"><th scope="col" className="py-1 pr-3">Model</th><th scope="col" className="py-1 pr-3">MAE (kWh/hour)</th><th scope="col" className="py-1">RMSE (kWh/hour)</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-t border-slate-100">
              <td className="py-1 pr-3">{row.label}</td>
              <td className="py-1 pr-3">{row.block.mae.toFixed(4)}</td>
              <td className="py-1">{row.block.rmse.toFixed(4)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="space-y-2 text-sm">
        {rows.filter((r) => r.diff).map((row) => (
          <div key={row.key} className="rounded-md bg-slate-50 p-3">
            <p className="font-medium text-slate-700">{row.label} against the baseline</p>
            {["mae", "rmse"].map((metric) => (
              <p key={metric} className="text-slate-600">
                {metric.toUpperCase()} difference {row.diff[metric].difference >= 0 ? "+" : ""}{row.diff[metric].difference.toFixed(4)} kWh,
                95% interval [{row.diff[metric].ci95[0].toFixed(4)}, {row.diff[metric].ci95[1].toFixed(4)}]: {row.diff[metric].verdict}
              </p>
            ))}
          </div>
        ))}
      </div>
      <ul className="list-disc space-y-1 pl-5 text-xs text-slate-500">
        {report.notes.map((note) => <li key={note}>{note}</li>)}
      </ul>
    </section>
  );
}

function EvaluationPanel({ labId }) {
  const evaluation = useAsync(() => (labId ? forecastsApi.evaluation(labId) : Promise.resolve(null)), [labId]);
  if (!labId) return null;
  if (evaluation.loading) return <LoadingState label="Evaluating the baseline…" />;
  if (evaluation.error) return <ErrorBanner error={evaluation.error} onRetry={evaluation.reload} />;
  const report = evaluation.data;
  if (!report) return null;

  return (
    <section className="card space-y-5">
      <div>
        <h2 className="text-sm font-semibold text-slate-700">Baseline accuracy on held-out data</h2>
        <p className="text-xs text-slate-500">{report.model} · times in {report.timezone}</p>
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-md bg-slate-50 p-3"><dt className="text-xs text-slate-500">Test MAE (per hour)</dt><dd className="text-xl font-semibold">{report.test.mae.toFixed(3)} kWh</dd></div>
        <div className="rounded-md bg-slate-50 p-3"><dt className="text-xs text-slate-500">Test RMSE (per hour)</dt><dd className="text-xl font-semibold">{report.test.rmse.toFixed(3)} kWh</dd></div>
        <div className="rounded-md bg-slate-50 p-3"><dt className="text-xs text-slate-500">Test days scored</dt><dd className="text-xl font-semibold">{report.test.days_evaluated}</dd></div>
        <div className="rounded-md bg-slate-50 p-3"><dt className="text-xs text-slate-500">Window k chosen on validation</dt><dd className="text-xl font-semibold">{report.chosen_k}</dd></div>
      </dl>

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-sm font-medium text-slate-700">Chronological split</h3>
          <table className="min-w-full text-sm">
            <thead><tr className="text-left text-xs uppercase text-slate-500"><th scope="col" className="py-1 pr-3">Period</th><th scope="col" className="py-1 pr-3">Dates</th><th scope="col" className="py-1">Days</th></tr></thead>
            <tbody>
              {["train", "validation", "test"].map((name) => (
                <tr key={name} className="border-t border-slate-100">
                  <td className="py-1 pr-3 capitalize">{name}</td>
                  <td className="py-1 pr-3">{report.split[name].start} to {report.split[name].end}</td>
                  <td className="py-1">{report.split[name].days}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <h3 className="mb-2 text-sm font-medium text-slate-700">Window choice on validation</h3>
          <table className="min-w-full text-sm">
            <thead><tr className="text-left text-xs uppercase text-slate-500"><th scope="col" className="py-1 pr-3">k</th><th scope="col" className="py-1 pr-3">MAE</th><th scope="col" className="py-1 pr-3">RMSE</th><th scope="col" className="py-1">Days</th></tr></thead>
            <tbody>
              {report.validation_selection.map((row) => (
                <tr key={row.k} className={`border-t border-slate-100 ${row.k === report.chosen_k ? "font-semibold text-emerald-900" : ""}`}>
                  <td className="py-1 pr-3">{row.k}</td>
                  <td className="py-1 pr-3">{row.mae.toFixed(3)}</td>
                  <td className="py-1 pr-3">{row.rmse.toFixed(3)}</td>
                  <td className="py-1">{row.days_evaluated}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {report.daily.length > 0 && (
        <Chart
          height={280}
          data={[
            { type: "scatter", mode: "lines+markers", name: "Actual daily total", x: report.daily.map((d) => d.date), y: report.daily.map((d) => kwhNumber(d.actual_kwh)) },
            { type: "scatter", mode: "lines+markers", name: "Baseline prediction", x: report.daily.map((d) => d.date), y: report.daily.map((d) => kwhNumber(d.predicted_kwh)) },
          ]}
          layout={{ yaxis: { title: "kWh per day" } }}
        />
      )}

      <ul className="list-disc space-y-1 pl-5 text-xs text-slate-500">
        {report.notes.map((note) => <li key={note}>{note}</li>)}
      </ul>
    </section>
  );
}

function SavedForecasts({ labId, timezone, refreshKey }) {
  const list = useAsync(() => (labId ? forecastsApi.list({ lab_id: labId }) : Promise.resolve([])), [labId, refreshKey]);
  if (!labId) return null;
  return (
    <section className="card overflow-hidden p-0">
      <h2 className="px-4 pt-4 text-sm font-semibold text-slate-700">Saved forecasts</h2>
      <ErrorBanner error={list.error} onRetry={list.reload} />
      {list.loading && <LoadingState />}
      {list.data?.length === 0 && <div className="p-4"><EmptyState title="No forecasts saved for this laboratory yet" /></div>}
      {list.data?.length > 0 && (
        <table className="mt-3 min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr><th scope="col" className="table-th">Day forecast</th><th scope="col" className="table-th text-right">Estimated total</th><th scope="col" className="table-th">Created</th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {list.data.map((f) => (
              <tr key={f.id}>
                <td className="table-td">{formatInZone(f.horizon_start, timezone)}</td>
                <td className="table-td text-right">{formatKwh(f.predicted_kwh, 2)}</td>
                <td className="table-td">{formatInZone(f.created_at, timezone)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export default function Forecasts() {
  const { can } = useAuth();
  const labs = useAsync(() => labsApi.list(), []);
  const [labId, setLabId] = useState("");
  const range = useAsync(() => (labId ? labsApi.dataRange(labId) : Promise.resolve(null)), [labId]);
  // Default to the day after the latest reading, so the first request is a day the data can support.
  const initialDate = range.data?.last_day ? dayAfter(range.data.last_day) : tomorrowInputValue();
  const [refreshKey, setRefreshKey] = useState(0);
  const lab = labs.data?.find((l) => String(l.id) === String(labId));

  return (
    <>
      <PageHeader
        title="Forecasts"
        description="Estimates for future days, with their accuracy measured on data the baseline had not seen. Estimates are never presented as measured consumption."
      />
      <ErrorBanner error={labs.error} onRetry={labs.reload} />
      {labs.loading && <LoadingState label="Loading laboratories…" />}
      {labs.data?.length === 0 && <EmptyState title="Create a laboratory and import readings first" />}

      {labs.data?.length > 0 && (
        <div className="space-y-6">
          <div className="card max-w-sm"><LabPicker labs={labs.data} value={labId} onChange={setLabId} /></div>
          {labId && (
            <>
              <GenerateForecast labId={labId} initialDate={initialDate}
                canCreate={can("forecasts:create")} onCreated={() => setRefreshKey((k) => k + 1)} />
              <EvaluationPanel labId={labId} />
              <ModelComparison />
              <SavedForecasts labId={labId} timezone={lab?.timezone ?? "UTC"} refreshKey={refreshKey} />
            </>
          )}
        </div>
      )}
    </>
  );
}
