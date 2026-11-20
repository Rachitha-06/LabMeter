import { useMemo, useState } from "react";
import Chart from "../components/Chart.jsx";
import { EmptyState, ErrorBanner, LoadingState, PageHeader } from "../components/States.jsx";
import EstimateCards from "../components/EstimateCards.jsx";
import { ApiError } from "../api/client.js";
import { analytics, labs as labsApi } from "../api/endpoints.js";
import { useAsync } from "../hooks/useAsync.js";
import {
  dateInputEndIso, dateInputStartIso, daysAgoInputValue, formatCount, formatKwh, kwhNumber, todayInputValue,
} from "../utils/format.js";

const TYPE_COLORS = { measured: "#047857", imported: "#0369a1", simulated: "#a16207" };
const TYPES = ["measured", "imported", "simulated"];

function Card({ label, value, note }) {
  return (
    <div className="card">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
      {note && <p className="mt-1 text-xs text-slate-500">{note}</p>}
    </div>
  );
}

function Filters({ value, onChange, labs }) {
  const set = (key) => (event) => onChange({ ...value, [key]: event.target.value });
  return (
    <div className="card mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
      <div>
        <label className="label" htmlFor="dash-start">From</label>
        <input id="dash-start" type="date" className="input" value={value.start} max={value.end} onChange={set("start")} />
      </div>
      <div>
        <label className="label" htmlFor="dash-end">To (inclusive)</label>
        <input id="dash-end" type="date" className="input" value={value.end} min={value.start} onChange={set("end")} />
      </div>
      <div>
        <label className="label" htmlFor="dash-gran">Group by</label>
        <select id="dash-gran" className="input" value={value.granularity} onChange={set("granularity")}>
          <option value="day">Day</option>
          <option value="week">Week</option>
          <option value="month">Month</option>
        </select>
      </div>
      <div>
        <label className="label" htmlFor="dash-lab">Laboratory</label>
        <select id="dash-lab" className="input" value={value.labId} onChange={set("labId")}>
          <option value="">All laboratories</option>
          {labs.map((lab) => (
            <option key={lab.id} value={lab.id}>{lab.name}</option>
          ))}
        </select>
      </div>
      <div className="flex items-end">
        <button type="button" className="btn-secondary w-full" onClick={() => onChange(defaultRange())}>
          Last 30 days
        </button>
      </div>
    </div>
  );
}

function defaultRange() {
  return { start: daysAgoInputValue(29), end: todayInputValue(), granularity: "day", labId: "" };
}

function summarise(buckets) {
  const totals = { measured: 0, imported: 0, simulated: 0, readings: 0, resets: 0 };
  for (const b of buckets) {
    for (const t of TYPES) totals[t] += kwhNumber(b[`${t}_kwh`]);
    totals.readings += b.reading_count;
    totals.resets += b.resets_flagged;
  }
  return totals;
}

function periodSeries(buckets) {
  const periods = [...new Set(buckets.map((b) => b.period))].sort();
  return TYPES.map((type) => ({
    type: "bar",
    name: type[0].toUpperCase() + type.slice(1),
    x: periods,
    y: periods.map((p) =>
      buckets.filter((b) => b.period === p).reduce((sum, b) => sum + kwhNumber(b[`${type}_kwh`]), 0),
    ),
    marker: { color: TYPE_COLORS[type] },
  }));
}

function labSeries(buckets) {
  const byLab = new Map();
  for (const b of buckets) byLab.set(b.lab_name, (byLab.get(b.lab_name) ?? 0) + kwhNumber(b.total_kwh));
  const names = [...byLab.keys()].sort();
  return [{ type: "bar", orientation: "h", x: names.map((n) => byLab.get(n)), y: names, marker: { color: "#059669" } }];
}

export default function Dashboard() {
  const [range, setRange] = useState(defaultRange);
  const labsState = useAsync(() => labsApi.list(), []);

  const invalid = !range.start || !range.end || range.end < range.start;
  const query = useAsync(() => {
    if (invalid) return Promise.reject(new ApiError(0, "invalid_range", "End date must be on or after the start date."));
    const params = {
      start: dateInputStartIso(range.start),
      end: dateInputEndIso(range.end),
      granularity: range.granularity,
    };
    if (range.labId) params.lab_id = range.labId;
    return analytics.consumption(params);
  }, [range.start, range.end, range.granularity, range.labId]);

  const buckets = query.data?.buckets ?? [];
  const totals = useMemo(() => summarise(buckets), [buckets]);

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Measured, imported and simulated energy for the selected period. Each laboratory's local time is used for grouping."
      />

      <Filters value={range} onChange={setRange} labs={labsState.data ?? []} />
      <ErrorBanner error={labsState.error} onRetry={labsState.reload} />

      {query.loading && <LoadingState label="Loading consumption…" />}
      <ErrorBanner error={query.error} onRetry={query.reload} />

      {!query.loading && !query.error && buckets.length === 0 && (
        <EmptyState title="No readings in this period">
          Import readings from the CSV page, or pick a wider date range.
        </EmptyState>
      )}

      {!query.loading && !query.error && buckets.length > 0 && (
        <>
          <EstimateCards start={dateInputStartIso(range.start)} end={dateInputEndIso(range.end)}
            labId={range.labId} />

          <section className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <Card label="Measured" value={formatKwh(totals.measured)} note="Energy recorded by meters" />
            <Card label="Imported" value={formatKwh(totals.imported)} note="Loaded from external files" />
            <Card label="Simulated" value={formatKwh(totals.simulated)} note="Synthetic data, not campus measurements" />
            <Card label="Readings" value={formatCount(totals.readings)} note={`${formatCount(totals.resets)} meter resets flagged`} />
          </section>

          {totals.simulated > 0 && (
            <div className="mb-6 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              This period includes simulated readings. They come from a generated dataset and must not be reported as
              measured consumption.
            </div>
          )}

          <section className="mb-6 grid gap-6 lg:grid-cols-3">
            <div className="card lg:col-span-2">
              <h2 className="mb-2 text-sm font-semibold text-slate-700">Consumption by period</h2>
              <Chart
                data={periodSeries(buckets)}
                layout={{ barmode: "stack", yaxis: { title: "kWh" }, xaxis: { type: "category" } }}
              />
            </div>
            <div className="card">
              <h2 className="mb-2 text-sm font-semibold text-slate-700">Total by laboratory</h2>
              <Chart data={labSeries(buckets)} layout={{ xaxis: { title: "kWh" }, margin: { t: 10, r: 16, b: 40, l: 140 } }} height={320} />
            </div>
          </section>

          <section className="card mb-8 overflow-hidden p-0">
            <div className="max-h-96 overflow-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="sticky top-0 bg-slate-50">
                  <tr>
                    <th scope="col" className="table-th">Period</th>
                    <th scope="col" className="table-th">Laboratory</th>
                    <th scope="col" className="table-th text-right">Measured</th>
                    <th scope="col" className="table-th text-right">Imported</th>
                    <th scope="col" className="table-th text-right">Simulated</th>
                    <th scope="col" className="table-th text-right">Readings</th>
                    <th scope="col" className="table-th text-right">Resets</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {buckets.map((b) => (
                    <tr key={`${b.lab_id}-${b.period}`}>
                      <td className="table-td">{b.period}</td>
                      <td className="table-td">{b.lab_name}</td>
                      <td className="table-td text-right">{formatKwh(b.measured_kwh)}</td>
                      <td className="table-td text-right">{formatKwh(b.imported_kwh)}</td>
                      <td className="table-td text-right">{formatKwh(b.simulated_kwh)}</td>
                      <td className="table-td text-right">{formatCount(b.reading_count)}</td>
                      <td className="table-td text-right">{formatCount(b.resets_flagged)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      <section className="card">
        <h2 className="mb-2 text-sm font-semibold text-slate-700">Not built yet</h2>
        <p className="mb-3 text-sm text-slate-500">
          Report generation and the deployment guide are planned for Phase 9.
        </p>
      </section>
    </>
  );
}
