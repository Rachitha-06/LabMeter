import { useState } from "react";
import { alerts as alertsApi, labs as labsApi } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { EmptyState, ErrorBanner, LoadingState, PageHeader, SuccessBanner } from "../components/States.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { formatKwh } from "../utils/format.js";

const STATUS_LABELS = { open: "Open", under_review: "Under review", resolved: "Resolved" };
const PAGE_SIZE = 50;
const SEVERITY_STYLES = {
  high: "bg-red-100 text-red-900",
  medium: "bg-amber-100 text-amber-900",
  low: "bg-slate-100 text-slate-700",
};

function Badge({ className, children }) {
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${className}`}>{children}</span>;
}

function DetectionSummary({ summary }) {
  if (!summary) return null;
  return (
    <SuccessBanner>
      Screening finished: {summary.created} new alert{summary.created === 1 ? "" : "s"}, {summary.already_recorded} already recorded.
      {" "}Days screened {summary.days_evaluated}; exam-period days skipped {summary.days_skipped_exam}; holidays
      skipped {summary.days_skipped_holiday}; hours without enough earlier days {summary.hours_without_history}.
      {summary.labs_without_schedule > 0 && ` ${summary.labs_without_schedule} laboratory without operating hours was not screened.`}
    </SuccessBanner>
  );
}

function ReviewPanel({ alertId, canReview, onChanged }) {
  const detail = useAsync(() => alertsApi.get(alertId), [alertId]);
  const [comment, setComment] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function move(status) {
    setBusy(true);
    setError(null);
    try {
      await alertsApi.update(alertId, { status, comment: comment.trim() || null });
      setComment("");
      detail.reload();
      onChanged();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function addComment() {
    setBusy(true);
    setError(null);
    try {
      await alertsApi.comment(alertId, comment.trim());
      setComment("");
      detail.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (detail.loading) return <LoadingState label="Loading alert…" />;
  if (detail.error) return <ErrorBanner error={detail.error} onRetry={detail.reload} />;
  const alert = detail.data;
  const needsComment = comment.trim().length === 0;

  return (
    <section className="card space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold text-slate-700">{alert.lab_name}</h2>
        <Badge className={SEVERITY_STYLES[alert.severity]}>{alert.severity} priority</Badge>
        <Badge className="bg-sky-100 text-sky-900">{STATUS_LABELS[alert.status]}</Badge>
      </div>
      <p className="text-sm text-slate-600">{alert.period_local}</p>
      <dl className="grid grid-cols-3 gap-3 text-sm">
        <div><dt className="text-xs text-slate-500">Used</dt><dd className="font-semibold">{formatKwh(alert.actual_kwh, 2)}</dd></div>
        <div><dt className="text-xs text-slate-500">Expected</dt><dd className="font-semibold">{alert.expected_kwh ? formatKwh(alert.expected_kwh, 2) : "—"}</dd></div>
        <div><dt className="text-xs text-slate-500">Excess</dt><dd className="font-semibold">{alert.difference_kwh ? formatKwh(alert.difference_kwh, 2) : "—"}</dd></div>
      </dl>
      <p className="rounded-md bg-slate-50 p-3 text-sm text-slate-700">{alert.explanation}</p>
      <p className="text-xs text-slate-500">
        Priority reflects how large the excess is, not how certain it is. Only a review can establish whether waste occurred.
      </p>

      {alert.reviews.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">History</h3>
          <ul className="space-y-1 text-sm">
            {alert.reviews.map((r) => (
              <li key={r.id} className="text-slate-600">
                {r.from_status === r.to_status ? "Comment" : `${STATUS_LABELS[r.from_status]} → ${STATUS_LABELS[r.to_status]}`}
                {r.comment && <span>: “{r.comment}”</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {canReview && (
        <div className="space-y-3 border-t border-slate-200 pt-4">
          <label className="label" htmlFor="alert-comment">Review note</label>
          <textarea id="alert-comment" className="input" rows={2} maxLength={1000} value={comment}
            onChange={(e) => setComment(e.target.value)} placeholder="What did you find? Required to resolve." />
          <div className="flex flex-wrap gap-2">
            {alert.status === "open" && (
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => move("under_review")}>Start review</button>
            )}
            {alert.status !== "resolved" && (
              <button type="button" className="btn-primary" disabled={busy || needsComment} onClick={() => move("resolved")}>
                Resolve
              </button>
            )}
            {alert.status === "under_review" && (
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => move("open")}>Return to open</button>
            )}
            {alert.status === "resolved" && (
              <button type="button" className="btn-secondary" disabled={busy} onClick={() => move("open")}>Reopen</button>
            )}
            <button type="button" className="btn-secondary" disabled={busy || needsComment} onClick={addComment}>Add note only</button>
          </div>
          <ErrorBanner error={error} />
        </div>
      )}
    </section>
  );
}

export default function Alerts() {
  const { can } = useAuth();
  const labs = useAsync(() => labsApi.list(), []);
  const [filters, setFilters] = useState({ lab_id: "", status: "" });
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const filterParams = {};
  if (filters.lab_id) filterParams.lab_id = filters.lab_id;
  if (filters.status) filterParams.status = filters.status;
  const list = useAsync(
    () => alertsApi.list({ ...filterParams, limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) }),
    [filters.lab_id, filters.status, page]);
  const total = useAsync(() => alertsApi.count(filterParams), [filters.lab_id, filters.status]);
  const totalCount = total.data?.total ?? 0;
  const firstShown = totalCount === 0 ? 0 : page * PAGE_SIZE + 1;
  const lastShown = Math.min(totalCount, (page + 1) * PAGE_SIZE);

  async function runScreening() {
    setBusy(true);
    setError(null);
    try {
      const body = filters.lab_id ? { lab_id: Number(filters.lab_id) } : {};
      setSummary(await alertsApi.detect(body));
      list.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Wastage alerts"
        description="Consumption outside scheduled hours that is well above what comparable earlier days used. Alerts are suspicions for review. None of them is a finding of waste."
        actions={can("alerts:detect") ? (
          <button type="button" className="btn-primary" disabled={busy} onClick={runScreening}>
            {busy ? "Screening…" : "Run screening"}
          </button>
        ) : null}
      />

      <DetectionSummary summary={summary} />
      <ErrorBanner error={error} />

      <section className="card mb-4 grid gap-3 sm:grid-cols-3">
        <div>
          <label className="label" htmlFor="al-lab">Laboratory</label>
          <select id="al-lab" className="input" value={filters.lab_id}
            onChange={(e) => { setPage(0); setFilters({ ...filters, lab_id: e.target.value }); }}>
            <option value="">All</option>
            {(labs.data ?? []).map((lab) => <option key={lab.id} value={lab.id}>{lab.name}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="al-status">Status</label>
          <select id="al-status" className="input" value={filters.status}
            onChange={(e) => { setPage(0); setFilters({ ...filters, status: e.target.value }); }}>
            <option value="">All</option>
            <option value="open">Open</option>
            <option value="under_review">Under review</option>
            <option value="resolved">Resolved</option>
          </select>
        </div>
      </section>

      {list.loading && <LoadingState label="Loading alerts…" />}
      <ErrorBanner error={list.error} onRetry={list.reload} />

      {list.data?.length === 0 && (
        <EmptyState title="No alerts match these filters">
          Run screening after readings and operating hours are loaded.
        </EmptyState>
      )}

      {totalCount > 0 && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm text-slate-600">
          <p aria-live="polite">Showing {firstShown}–{lastShown} of {totalCount} alerts</p>
          <div className="flex gap-2">
            <button type="button" className="btn-secondary" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</button>
            <button type="button" className="btn-secondary" disabled={lastShown >= totalCount}
              onClick={() => setPage((p) => p + 1)}>Next</button>
          </div>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        {list.data?.length > 0 && (
          <div className="card overflow-hidden p-0 lg:col-span-3">
            <div className="max-h-[32rem] overflow-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="sticky top-0 bg-slate-50">
                  <tr>
                    <th scope="col" className="table-th">Period</th>
                    <th scope="col" className="table-th">Laboratory</th>
                    <th scope="col" className="table-th text-right">Excess</th>
                    <th scope="col" className="table-th">Priority</th>
                    <th scope="col" className="table-th">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {list.data.map((a) => (
                    <tr key={a.id} className={`hover:bg-slate-50 ${selected === a.id ? "bg-emerald-50" : ""}`}>
                      <td className="table-td whitespace-nowrap">
                        <button type="button" onClick={() => setSelected(a.id)} aria-pressed={selected === a.id}
                          className="text-left text-emerald-900 underline-offset-2 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600">
                          {a.period_local}
                        </button>
                      </td>
                      <td className="table-td">{a.lab_name}</td>
                      <td className="table-td text-right">{a.difference_kwh ? formatKwh(a.difference_kwh, 2) : "—"}</td>
                      <td className="table-td"><Badge className={SEVERITY_STYLES[a.severity]}>{a.severity}</Badge></td>
                      <td className="table-td">{STATUS_LABELS[a.status]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        <div className="lg:col-span-2">
          {selected ? (
            <ReviewPanel key={selected} alertId={selected} canReview={can("alerts:review")} onChanged={list.reload} />
          ) : (
            list.data?.length > 0 && <p className="text-sm text-slate-500">Select an alert to read its explanation and review it.</p>
          )}
        </div>
      </div>
    </>
  );
}
