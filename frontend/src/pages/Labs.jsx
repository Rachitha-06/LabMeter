import { useState } from "react";
import { Link } from "react-router-dom";
import { labs as labsApi } from "../api/endpoints.js";
import { ErrorBanner, EmptyState, LoadingState, PageHeader, SuccessBanner } from "../components/States.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { useAuth } from "../auth/AuthContext.jsx";

const TIMEZONES = ["Asia/Kolkata", "UTC", "Europe/London", "America/New_York", "Asia/Singapore"];

export function LabForm({ initial = {}, submitLabel, onSubmit, busy }) {
  const [form, setForm] = useState({
    name: initial.name ?? "",
    building: initial.building ?? "",
    lab_type: initial.lab_type ?? "Teaching",
    computer_count: initial.computer_count ?? 30,
    timezone: initial.timezone ?? "Asia/Kolkata",
  });
  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value });

  return (
    <form
      className="grid gap-4 sm:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit({ ...form, computer_count: Number(form.computer_count) });
      }}
    >
      <div>
        <label className="label" htmlFor="lab-name">Name</label>
        <input id="lab-name" className="input" required maxLength={120} value={form.name} onChange={set("name")} />
      </div>
      <div>
        <label className="label" htmlFor="lab-building">Building or block</label>
        <input id="lab-building" className="input" required maxLength={120} value={form.building} onChange={set("building")} />
      </div>
      <div>
        <label className="label" htmlFor="lab-type">Laboratory type</label>
        <input id="lab-type" className="input" required maxLength={60} value={form.lab_type} onChange={set("lab_type")} />
      </div>
      <div>
        <label className="label" htmlFor="lab-computers">Number of computers</label>
        <input id="lab-computers" type="number" min={0} max={5000} className="input" required value={form.computer_count} onChange={set("computer_count")} />
      </div>
      <div className="sm:col-span-2">
        <label className="label" htmlFor="lab-tz">Timezone (IANA name)</label>
        <input id="lab-tz" list="timezone-options" className="input" required value={form.timezone} onChange={set("timezone")} />
        <datalist id="timezone-options">
          {TIMEZONES.map((tz) => <option key={tz} value={tz} />)}
        </datalist>
      </div>
      <div className="sm:col-span-2">
        <button type="submit" className="btn-primary" disabled={busy}>{submitLabel}</button>
      </div>
    </form>
  );
}

export default function Labs() {
  const { can } = useAuth();
  const [includeArchived, setIncludeArchived] = useState(false);
  const labs = useAsync(() => labsApi.list(includeArchived), [includeArchived]);
  const [actionError, setActionError] = useState(null);

  async function toggleArchive(lab) {
    setActionError(null);
    try {
      if (lab.archived_at) await labsApi.restore(lab.id);
      else await labsApi.archive(lab.id);
      labs.reload();
    } catch (err) {
      setActionError(err);
    }
  }
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [message, setMessage] = useState(null);

  async function create(body) {
    setBusy(true);
    setSaveError(null);
    setMessage(null);
    try {
      const lab = await labsApi.create(body);
      setMessage(`Created “${lab.name}”.`);
      setShowForm(false);
      labs.reload();
    } catch (error) {
      setSaveError(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Laboratories"
        description="Each laboratory has its own timezone, which is used for daily totals and display."
        actions={can("labs:write") ? (
          <button type="button" className="btn-primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Close" : "New laboratory"}
          </button>
        ) : null}
      />

      <SuccessBanner>{message}</SuccessBanner>
      {showForm && can("labs:write") && (
        <section className="card mb-6">
          <ErrorBanner error={saveError} />
          <LabForm submitLabel="Create laboratory" onSubmit={create} busy={busy} />
        </section>
      )}

      <label className="mb-3 flex items-center gap-2 text-sm text-slate-600">
        <input type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)} />
        Show archived laboratories
      </label>
      <ErrorBanner error={actionError} />
      {labs.loading && <LoadingState label="Loading laboratories…" />}
      <ErrorBanner error={labs.error} onRetry={labs.reload} />

      {!labs.loading && !labs.error && labs.data?.length === 0 && (
        <EmptyState title="No laboratories yet">Create one to start recording readings.</EmptyState>
      )}

      {labs.data?.length > 0 && (
        <div className="card overflow-hidden p-0">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th scope="col" className="table-th">Name</th>
                <th scope="col" className="table-th">Building</th>
                <th scope="col" className="table-th">Type</th>
                <th scope="col" className="table-th text-right">Computers</th>
                <th scope="col" className="table-th">Timezone</th>
                <th scope="col" className="table-th">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {labs.data.map((lab) => (
                <tr key={lab.id} className="hover:bg-slate-50">
                  <td className="table-td">
                    <Link className="font-medium text-emerald-800 hover:underline" to={`/labs/${lab.id}`}>{lab.name}</Link>
                  </td>
                  <td className="table-td">{lab.building}</td>
                  <td className="table-td">{lab.lab_type}</td>
                  <td className="table-td text-right">{lab.computer_count}</td>
                  <td className="table-td">{lab.timezone}</td>
                  <td className="table-td whitespace-nowrap">
                    {lab.archived_at ? <span className="mr-2 rounded bg-slate-200 px-2 py-0.5 text-xs">Archived</span> : null}
                    {can("labs:write") && (
                      <button type="button" className="text-xs text-emerald-800 underline" onClick={() => toggleArchive(lab)}>
                        {lab.archived_at ? "Restore" : "Archive"}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
