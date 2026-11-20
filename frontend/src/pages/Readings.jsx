import { Fragment, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { labs as labsApi, readings as readingsApi } from "../api/endpoints.js";
import { ApiError } from "../api/client.js";
import { EmptyState, ErrorBanner, LoadingState, PageHeader, SuccessBanner } from "../components/States.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { formatInZone, formatKwh, localInputToIso } from "../utils/format.js";

const PAGE_SIZE = 50;

function labNameMap(labs) {
  return new Map((labs ?? []).map((lab) => [lab.id, lab]));
}

/** Plain-language result for a create request. Duplicates and conflicts are shown explicitly. */
function describeOutcome(outcome) {
  if (outcome.status === "created") return `Reading saved (id ${outcome.reading.id}).`;
  return "This reading is already stored with the same value. Nothing was changed.";
}

function ReadingForm({ labs, onSaved }) {
  const [form, setForm] = useState({
    lab_id: labs[0]?.id ?? "",
    timestamp: "",
    value: "",
    unit: "kWh",
    reading_type: "measured",
    meter_id: "",
    source: "manual",
  });
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  async function submit(event) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    const iso = localInputToIso(form.timestamp);
    if (!iso) {
      setError(new ApiError(0, "invalid_timestamp", "Enter a valid date and time."));
      return;
    }
    setBusy(true);
    try {
      const outcome = await readingsApi.create({
        lab_id: Number(form.lab_id),
        timestamp: iso,
        value: String(form.value),
        unit: form.unit,
        reading_type: form.reading_type,
        meter_id: form.meter_id || null,
        source: form.source || "manual",
      });
      setNotice(describeOutcome(outcome));
      onSaved();
    } catch (err) {
      if (err.code === "reading_conflict") {
        const d = err.details ?? {};
        setError(new ApiError(err.status, err.code,
          `A different value is already stored for this time: ${formatKwh(d.existing_interval_kwh, 4)}. ` +
          "Correct the existing reading from the table below instead.", d));
      } else {
        setError(err);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" onSubmit={submit}>
      <div>
        <label className="label" htmlFor="rd-lab">Laboratory</label>
        <select id="rd-lab" className="input" required value={form.lab_id} onChange={set("lab_id")}>
          {labs.map((lab) => <option key={lab.id} value={lab.id}>{lab.name}</option>)}
        </select>
      </div>
      <div>
        <label className="label" htmlFor="rd-time">Time (your local time)</label>
        <input id="rd-time" type="datetime-local" className="input" required value={form.timestamp} onChange={set("timestamp")} />
      </div>
      <div>
        <label className="label" htmlFor="rd-value">Amount</label>
        <input id="rd-value" type="number" step="0.0001" min="0" className="input" required value={form.value} onChange={set("value")} />
      </div>
      <div>
        <label className="label" htmlFor="rd-unit">Unit</label>
        <select id="rd-unit" className="input" value={form.unit} onChange={set("unit")}>
          <option value="kWh">kWh</option>
          <option value="Wh">Wh</option>
        </select>
      </div>
      <div>
        <label className="label" htmlFor="rd-type">Type</label>
        <select id="rd-type" className="input" value={form.reading_type} onChange={set("reading_type")}>
          <option value="measured">Measured</option>
          <option value="imported">Imported</option>
          <option value="simulated">Simulated</option>
        </select>
      </div>
      <div>
        <label className="label" htmlFor="rd-meter">Meter (optional)</label>
        <input id="rd-meter" className="input" maxLength={64} value={form.meter_id} onChange={set("meter_id")} />
      </div>
      <div>
        <label className="label" htmlFor="rd-source">Source</label>
        <input id="rd-source" className="input" maxLength={120} value={form.source} onChange={set("source")} />
      </div>
      <div className="flex items-end">
        <button type="submit" className="btn-primary w-full" disabled={busy || labs.length === 0}>
          {busy ? "Saving…" : "Save reading"}
        </button>
      </div>
      <div className="sm:col-span-4">
        <ErrorBanner error={error} />
        <SuccessBanner>{notice}</SuccessBanner>
      </div>
    </form>
  );
}

function CorrectReading({ reading, onDone }) {
  const [value, setValue] = useState(reading.interval_kwh);
  const [reason, setReason] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await readingsApi.correct(reading.id, { interval_kwh: String(value), reason });
      onDone("Correction saved. The previous value is kept in the history.");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="grid gap-2 bg-slate-50 p-3 sm:grid-cols-[1fr_2fr_auto]" onSubmit={submit}>
      <input aria-label="Corrected kWh" type="number" step="0.0001" min="0" className="input" required value={value} onChange={(e) => setValue(e.target.value)} />
      <input aria-label="Reason for correction" className="input" required minLength={5} placeholder="Reason (at least 5 characters)" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="flex gap-2">
        <button type="submit" className="btn-primary" disabled={busy}>Save</button>
        <button type="button" className="btn-secondary" onClick={() => onDone(null)}>Cancel</button>
      </div>
      <div className="sm:col-span-3"><ErrorBanner error={error} /></div>
    </form>
  );
}

function History({ readingId }) {
  const history = useAsync(() => readingsApi.revisions(readingId), [readingId]);
  if (history.loading) return <LoadingState label="Loading history…" />;
  if (history.error) return <ErrorBanner error={history.error} />;
  if (!history.data.length) return <p className="p-3 text-sm text-slate-500">No corrections yet.</p>;
  return (
    <ul className="space-y-1 bg-slate-50 p-3 text-sm">
      {history.data.map((r) => (
        <li key={r.id}>
          {formatKwh(r.old_interval_kwh, 4)} → {formatKwh(r.new_interval_kwh, 4)} · “{r.reason}”
        </li>
      ))}
    </ul>
  );
}

export default function Readings() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  const [page, setPage] = useState(0);
  const [filters, setFilters] = useState({
    lab_id: params.get("lab_id") ?? "",
    start: "",
    end: "",
    reading_type: "",
  });
  const [editing, setEditing] = useState(null);
  const [showHistory, setShowHistory] = useState(null);
  const [notice, setNotice] = useState(null);
  const [showForm, setShowForm] = useState(false);

  const labs = useAsync(() => labsApi.list(), []);
  const labMap = labNameMap(labs.data);

  const query = {
    limit: String(PAGE_SIZE),
    offset: String(page * PAGE_SIZE),
  };
  if (filters.lab_id) query.lab_id = filters.lab_id;
  if (filters.reading_type) query.reading_type = filters.reading_type;
  const start = localInputToIso(filters.start);
  const end = localInputToIso(filters.end);
  if (start) query.start = start;
  if (end) query.end = end;

  const list = useAsync(() => readingsApi.list(query), [JSON.stringify(query)]);

  const applyFilter = (next) => {
    setPage(0);
    setFilters({ ...filters, ...next });
    const copy = new URLSearchParams(params);
    if (next.lab_id) copy.set("lab_id", next.lab_id);
    else copy.delete("lab_id");
    setParams(copy, { replace: true });
  };

  return (
    <>
      <PageHeader
        title="Readings"
        description="Stored interval readings. Corrections keep the original value. Times are shown in each laboratory's timezone."
        actions={can("readings:write") ? (
          <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Close" : "Add reading"}
          </button>
        ) : null}
      />

      {showForm && can("readings:write") && labs.data?.length > 0 && (
        <section className="card mb-6">
          <ReadingForm labs={labs.data} onSaved={() => list.reload()} />
        </section>
      )}
      {showForm && labs.data?.length === 0 && (
        <EmptyState title="Create a laboratory first">Readings belong to a laboratory.</EmptyState>
      )}

      <section className="card mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label className="label" htmlFor="f-lab">Laboratory</label>
          <select id="f-lab" className="input" value={filters.lab_id} onChange={(e) => applyFilter({ lab_id: e.target.value })}>
            <option value="">All</option>
            {(labs.data ?? []).map((lab) => <option key={lab.id} value={lab.id}>{lab.name}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="f-start">From (local)</label>
          <input id="f-start" type="datetime-local" className="input" value={filters.start} onChange={(e) => applyFilter({ start: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="f-end">To (local)</label>
          <input id="f-end" type="datetime-local" className="input" value={filters.end} onChange={(e) => applyFilter({ end: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="f-type">Type</label>
          <select id="f-type" className="input" value={filters.reading_type} onChange={(e) => applyFilter({ reading_type: e.target.value })}>
            <option value="">All</option>
            <option value="measured">Measured</option>
            <option value="imported">Imported</option>
            <option value="simulated">Simulated</option>
          </select>
        </div>
      </section>

      <SuccessBanner>{notice}</SuccessBanner>
      <ErrorBanner error={labs.error} onRetry={labs.reload} />
      <ErrorBanner error={list.error} onRetry={list.reload} />
      {list.loading && <LoadingState label="Loading readings…" />}

      {!list.loading && !list.error && list.data?.length === 0 && (
        <EmptyState title="No readings match these filters" />
      )}

      {list.data?.length > 0 && (
        <div className="card overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50">
                <tr>
                  <th scope="col" className="table-th">Time</th>
                  <th scope="col" className="table-th">Laboratory</th>
                  <th scope="col" className="table-th">Meter</th>
                  <th scope="col" className="table-th text-right">Energy</th>
                  <th scope="col" className="table-th">Type</th>
                  <th scope="col" className="table-th">Flag</th>
                  <th scope="col" className="table-th">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {list.data.map((r) => {
                  const lab = labMap.get(r.lab_id);
                  const open = editing === r.id || showHistory === r.id;
                  return (
                    <Fragment key={r.id}>
                    <tr className="align-top">
                      <td className="table-td whitespace-nowrap">{formatInZone(r.timestamp_utc, lab?.timezone ?? "UTC")}</td>
                      <td className="table-td">{lab?.name ?? `Lab ${r.lab_id}`}</td>
                      <td className="table-td">{r.meter_id}</td>
                      <td className="table-td text-right whitespace-nowrap">{formatKwh(r.interval_kwh, 4)}</td>
                      <td className="table-td">{r.reading_type}</td>
                      <td className="table-td">{r.quality_flag ? <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-900">{r.quality_flag}</span> : "—"}</td>
                      <td className="table-td whitespace-nowrap">
                        {can("readings:correct") && <button type="button" className="text-emerald-800 underline" onClick={() => setEditing(editing === r.id ? null : r.id)}>Correct</button>}
                        {can("readings:correct") && <span className="mx-2 text-slate-300">|</span>}
                        <button type="button" className="text-slate-600 underline" onClick={() => setShowHistory(showHistory === r.id ? null : r.id)}>History</button>
                      </td>
                    </tr>
                    {open && (
                      <tr>
                        <td colSpan={7} className="p-0">
                          {editing === r.id && (
                            <CorrectReading
                              reading={r}
                              onDone={(message) => {
                                setEditing(null);
                                if (message) {
                                  setNotice(message);
                                  list.reload();
                                }
                              }}
                            />
                          )}
                          {showHistory === r.id && <History readingId={r.id} />}
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-slate-200 px-3 py-2 text-sm">
            <button type="button" className="btn-secondary" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</button>
            <span className="text-slate-500">Page {page + 1}</span>
            <button type="button" className="btn-secondary" disabled={list.data.length < PAGE_SIZE} onClick={() => setPage((p) => p + 1)}>Next</button>
          </div>
        </div>
      )}
    </>
  );
}
