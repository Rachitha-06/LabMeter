import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { labs as labsApi } from "../api/endpoints.js";
import { EmptyState, ErrorBanner, LoadingState, PageHeader, SuccessBanner } from "../components/States.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { WEEKDAYS } from "../utils/format.js";
import { LabForm } from "./Labs.jsx";
import { useAuth } from "../auth/AuthContext.jsx";

function EquipmentSection({ labId }) {
  const list = useAsync(() => labsApi.equipment(labId), [labId]);
  const [form, setForm] = useState({ equipment_type: "", quantity: 1, rated_power_w: "" });
  const [error, setError] = useState(null);
  const [ok, setOk] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setError(null);
    setOk(null);
    try {
      await labsApi.addEquipment(labId, {
        equipment_type: form.equipment_type,
        quantity: Number(form.quantity),
        rated_power_w: form.rated_power_w === "" ? null : String(form.rated_power_w),
      });
      setOk("Equipment added.");
      setForm({ equipment_type: "", quantity: 1, rated_power_w: "" });
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="card">
      <h2 className="mb-3 text-sm font-semibold text-slate-700">Equipment</h2>
      <ErrorBanner error={list.error} onRetry={list.reload} />
      {list.loading && <LoadingState />}
      {list.data?.length === 0 && <EmptyState title="No equipment recorded" />}
      {list.data?.length > 0 && (
        <ul className="mb-4 divide-y divide-slate-100 text-sm">
          {list.data.map((item) => (
            <li key={item.id} className="flex justify-between py-2">
              <span>{item.equipment_type} × {item.quantity}</span>
              <span className="text-slate-500">{item.rated_power_w ? `${item.rated_power_w} W each` : "power not recorded"}</span>
            </li>
          ))}
        </ul>
      )}
      <form className="grid gap-3 sm:grid-cols-4" onSubmit={submit}>
        <input aria-label="Equipment type" className="input sm:col-span-2" placeholder="Type, e.g. monitor" required value={form.equipment_type} onChange={(e) => setForm({ ...form, equipment_type: e.target.value })} />
        <input aria-label="Quantity" type="number" min={0} className="input" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} />
        <input aria-label="Rated power in watts" type="number" min={0} step="0.01" className="input" placeholder="Watts (optional)" value={form.rated_power_w} onChange={(e) => setForm({ ...form, rated_power_w: e.target.value })} />
        <div className="sm:col-span-4">
          <button type="submit" className="btn-secondary">Add equipment</button>
        </div>
      </form>
      <div className="mt-3"><ErrorBanner error={error} /></div>
      <SuccessBanner>{ok}</SuccessBanner>
    </section>
  );
}

function ScheduleSection({ labId }) {
  const list = useAsync(() => labsApi.schedules(labId), [labId]);
  const [form, setForm] = useState({ weekday: 0, open_time: "08:00", close_time: "18:00", valid_from: "", valid_to: "" });
  const [error, setError] = useState(null);
  const [ok, setOk] = useState(null);

  async function submit(event) {
    event.preventDefault();
    setError(null);
    setOk(null);
    try {
      await labsApi.addSchedule(labId, {
        weekday: Number(form.weekday),
        open_time: `${form.open_time}:00`,
        close_time: `${form.close_time}:00`,
        valid_from: form.valid_from,
        valid_to: form.valid_to || null,
      });
      setOk("Schedule added.");
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="card">
      <h2 className="mb-3 text-sm font-semibold text-slate-700">Operating hours</h2>
      <p className="mb-3 text-xs text-slate-500">
        Days without a schedule are treated as closed. Overnight hours are not supported yet.
      </p>
      <ErrorBanner error={list.error} onRetry={list.reload} />
      {list.loading && <LoadingState />}
      {list.data?.length === 0 && <EmptyState title="No schedules recorded" />}
      {list.data?.length > 0 && (
        <table className="mb-4 min-w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-slate-500">
              <th scope="col" className="py-1 pr-3">Day</th><th scope="col" className="py-1 pr-3">Hours</th><th scope="col" className="py-1 pr-3">Valid</th>
            </tr>
          </thead>
          <tbody>
            {list.data.map((s) => (
              <tr key={s.id} className="border-t border-slate-100">
                <td className="py-1 pr-3">{WEEKDAYS[s.weekday]}</td>
                <td className="py-1 pr-3">{s.open_time.slice(0, 5)}–{s.close_time.slice(0, 5)}</td>
                <td className="py-1 pr-3">{s.valid_from} to {s.valid_to ?? "open-ended"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form className="grid gap-3 sm:grid-cols-3" onSubmit={submit}>
        <div>
          <label className="label" htmlFor="sch-day">Day</label>
          <select id="sch-day" className="input" value={form.weekday} onChange={(e) => setForm({ ...form, weekday: e.target.value })}>
            {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="sch-open">Opens</label>
          <input id="sch-open" type="time" className="input" required value={form.open_time} onChange={(e) => setForm({ ...form, open_time: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="sch-close">Closes</label>
          <input id="sch-close" type="time" className="input" required value={form.close_time} onChange={(e) => setForm({ ...form, close_time: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="sch-from">Valid from</label>
          <input id="sch-from" type="date" className="input" required value={form.valid_from} onChange={(e) => setForm({ ...form, valid_from: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="sch-to">Valid to (optional)</label>
          <input id="sch-to" type="date" className="input" value={form.valid_to} onChange={(e) => setForm({ ...form, valid_to: e.target.value })} />
        </div>
        <div className="flex items-end">
          <button type="submit" className="btn-secondary w-full">Add schedule</button>
        </div>
      </form>
      <div className="mt-3"><ErrorBanner error={error} /></div>
      <SuccessBanner>{ok}</SuccessBanner>
    </section>
  );
}

export default function LabDetail() {
  const { id } = useParams();
  const { can } = useAuth();
  const lab = useAsync(() => labsApi.get(id), [id]);
  const [busy, setBusy] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [saved, setSaved] = useState(null);

  async function save(body) {
    setBusy(true);
    setSaveError(null);
    setSaved(null);
    try {
      await labsApi.update(id, body);
      setSaved("Changes saved.");
      lab.reload();
    } catch (error) {
      setSaveError(error);
    } finally {
      setBusy(false);
    }
  }

  if (lab.loading) return <LoadingState label="Loading laboratory…" />;
  if (lab.error) {
    return (
      <>
        <ErrorBanner error={lab.error} onRetry={lab.reload} />
        <Link className="mt-4 inline-block text-sm text-emerald-800 underline" to="/labs">Back to laboratories</Link>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={lab.data.name}
        description={`${lab.data.building} · ${lab.data.lab_type} · ${lab.data.timezone}`}
        actions={<Link className="btn-secondary" to={`/readings?lab_id=${id}`}>View readings</Link>}
      />
      {!can("labs:write") && <p className="mb-4 text-sm text-slate-500">Read-only for your role.</p>}
      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card">
          <h2 className="mb-3 text-sm font-semibold text-slate-700">Details</h2>
          <ErrorBanner error={saveError} />
          <SuccessBanner>{saved}</SuccessBanner>
          <fieldset disabled={!can("labs:write")} className="contents">
            <LabForm key={lab.data.id} initial={lab.data} submitLabel="Save changes" onSubmit={save} busy={busy} />
          </fieldset>
        </section>
        <div className="grid content-start gap-6">
          <fieldset disabled={!can("labs:write")} className="contents">
            <EquipmentSection labId={id} />
            <ScheduleSection labId={id} />
          </fieldset>
        </div>
      </div>
    </>
  );
}
