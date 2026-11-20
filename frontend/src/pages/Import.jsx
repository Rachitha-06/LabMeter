import { useState } from "react";
import { imports as importsApi } from "../api/endpoints.js";
import { ErrorBanner, PageHeader, SuccessBanner } from "../components/States.jsx";
import { formatCount } from "../utils/format.js";
import { useAuth } from "../auth/AuthContext.jsx";

const PROBLEM_LIMIT = 200;

const COUNTERS = [
  ["accepted", "Accepted"],
  ["duplicates", "Duplicates (skipped)"],
  ["conflicts", "Conflicts (not overwritten)"],
  ["rejected", "Rejected"],
  ["skipped_baseline", "First cumulative reading"],
  ["skipped_gap", "Gap (not attributed)"],
  ["resets_flagged", "Meter resets flagged"],
];

function Results({ result }) {
  const problems = result.problems ?? [];
  return (
    <section className="card space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-700">
          {result.dry_run ? "Dry run: nothing was written" : `Imported as batch ${result.batch_id}`}
        </h2>
        <p className="text-sm text-slate-500">{formatCount(result.rows_total)} rows read</p>
      </div>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {COUNTERS.map(([key, label]) => (
          <div key={key} className="rounded-md bg-slate-50 p-3">
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd className="text-xl font-semibold text-slate-900">{formatCount(result[key])}</dd>
          </div>
        ))}
      </dl>
      {problems.length > 0 && (
        <div>
          <p className="mb-2 text-sm font-medium text-slate-700">
            Row details{problems.length >= PROBLEM_LIMIT ? ` (first ${PROBLEM_LIMIT} shown)` : ""}
          </p>
          <div className="max-h-72 overflow-auto rounded-md border border-slate-200">
            <table className="min-w-full text-sm">
              <thead className="sticky top-0 bg-slate-50">
                <tr>
                  <th scope="col" className="table-th">Row</th>
                  <th scope="col" className="table-th">Outcome</th>
                  <th scope="col" className="table-th">Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {problems.map((p, i) => (
                  <tr key={`${p.row}-${i}`}>
                    <td className="table-td">{p.row}</td>
                    <td className="table-td">{p.kind}</td>
                    <td className="table-td">
                      {p.reason}
                      {p.existing_kwh && <span className="text-slate-500"> (stored {p.existing_kwh}, file {p.new_kwh})</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

export default function Import() {
  const { can } = useAuth();
  const [file, setFile] = useState(null);
  const [intervalMinutes, setIntervalMinutes] = useState(60);
  const [check, setCheck] = useState(null);
  const [imported, setImported] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run(dryRun) {
    if (!file) return;
    setBusy(true);
    setError(null);
    if (dryRun) setImported(null);
    try {
      const result = await importsApi.upload(file, { dryRun, intervalMinutes });
      if (dryRun) setCheck(result);
      else {
        setImported(result);
        setCheck(null);
      }
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const canImport = check && check.accepted > 0;

  return (
    <>
      <PageHeader
        title="CSV import"
        description="Check a file first. Nothing is written until you confirm the import."
      />

      {!can("imports:write") && (
        <p className="mb-4 text-sm text-slate-500">Read-only: your role can view import results but not upload files.</p>
      )}
      <div className="grid gap-6 lg:grid-cols-3">
        <section className="card space-y-4 lg:col-span-1">
          <div>
            <label className="label" htmlFor="csv-file">Readings file</label>
            <input
              id="csv-file"
              disabled={!can("imports:write")}
              type="file"
              accept=".csv,text/csv"
              className="block w-full text-sm"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setCheck(null);
                setImported(null);
                setError(null);
              }}
            />
          </div>
          <div>
            <label className="label" htmlFor="csv-interval">Reading spacing (minutes)</label>
            <input id="csv-interval" type="number" min={1} max={1440} className="input" value={intervalMinutes} onChange={(e) => setIntervalMinutes(Number(e.target.value))} />
            <p className="mt-1 text-xs text-slate-500">Used to detect gaps in cumulative meter files.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-secondary" disabled={!file || busy || !can("imports:write")} onClick={() => run(true)}>
              {busy && !canImport ? "Checking…" : "Check file"}
            </button>
            <button type="button" className="btn-primary" disabled={!canImport || busy || !can("imports:write")} onClick={() => run(false)}>
              {canImport ? `Import ${formatCount(check.accepted)} readings` : "Import"}
            </button>
          </div>
          <div className="rounded-md bg-slate-50 p-3 text-xs text-slate-600">
            <p className="mb-1 font-medium">Expected columns</p>
            <p>lab_name or lab_id · timestamp (with offset) · value, interval_kwh, or cumulative_kwh · reading_type</p>
            <p className="mt-2">Optional: meter_id, unit (kWh or Wh), source. Up to 5 MB and 50,000 rows.</p>
          </div>
        </section>

        <div className="space-y-6 lg:col-span-2">
          <ErrorBanner error={error} />
          <SuccessBanner>
            {imported && `Import finished. ${formatCount(imported.accepted)} readings stored in batch ${imported.batch_id}.`}
          </SuccessBanner>
          {check && <Results result={check} />}
          {imported && <Results result={imported} />}
          {!check && !imported && !error && (
            <p className="text-sm text-slate-500">Choose a file and check it to see what would be stored.</p>
          )}
        </div>
      </div>
    </>
  );
}
