import { useState } from "react";
import { energy as energyApi } from "../api/endpoints.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { EmptyState, ErrorBanner, LoadingState, PageHeader, SuccessBanner } from "../components/States.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { WEEKDAYS, todayInputValue } from "../utils/format.js";

const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function TariffForm({ onCreated }) {
  const [form, setForm] = useState({
    rate_per_kwh: "", currency: "", effective_from: todayInputValue(), effective_to: "",
    time_band: "", start_hour: 0, end_hour: 24, weekdays: [0, 1, 2, 3, 4, 5, 6], source: "",
  });
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  const toggleDay = (day) => setForm({
    ...form,
    weekdays: form.weekdays.includes(day) ? form.weekdays.filter((d) => d !== day) : [...form.weekdays, day].sort(),
  });

  async function submit(event) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    const every = form.weekdays.length === 7;
    try {
      await energyApi.createTariff({
        rate_per_kwh: String(form.rate_per_kwh),
        currency: form.currency.trim().toUpperCase(),
        effective_from: form.effective_from,
        effective_to: form.effective_to || null,
        time_band: form.time_band || null,
        start_hour: Number(form.start_hour),
        end_hour: Number(form.end_hour),
        weekdays: every ? null : form.weekdays,
        source: form.source,
      });
      setNotice("Tariff band saved.");
      onCreated();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" onSubmit={submit}>
      <div><label className="label" htmlFor="t-rate">Rate per kWh</label>
        <input id="t-rate" type="number" step="0.0001" min="0" required className="input" value={form.rate_per_kwh} onChange={set("rate_per_kwh")} /></div>
      <div><label className="label" htmlFor="t-currency">Currency code</label>
        <input id="t-currency" required className="input" placeholder="e.g. INR" value={form.currency} onChange={set("currency")} /></div>
      <div><label className="label" htmlFor="t-from">Effective from</label>
        <input id="t-from" type="date" required className="input" value={form.effective_from} onChange={set("effective_from")} /></div>
      <div><label className="label" htmlFor="t-to">Effective to (optional)</label>
        <input id="t-to" type="date" className="input" value={form.effective_to} onChange={set("effective_to")} /></div>
      <div><label className="label" htmlFor="t-band">Band name (optional)</label>
        <input id="t-band" className="input" value={form.time_band} onChange={set("time_band")} /></div>
      <div><label className="label" htmlFor="t-start">Starts at hour</label>
        <input id="t-start" type="number" min={0} max={23} className="input" value={form.start_hour} onChange={set("start_hour")} /></div>
      <div><label className="label" htmlFor="t-end">Ends before hour</label>
        <input id="t-end" type="number" min={1} max={24} className="input" value={form.end_hour} onChange={set("end_hour")} /></div>
      <fieldset className="sm:col-span-2">
        <legend className="label">Weekdays</legend>
        <div className="flex flex-wrap gap-3 text-sm">
          {DAY_LABELS.map((label, day) => (
            <label key={label} className="flex items-center gap-1">
              <input type="checkbox" checked={form.weekdays.includes(day)} onChange={() => toggleDay(day)} />
              {label}
            </label>
          ))}
        </div>
        <p className="mt-1 text-xs text-slate-500">All seven days selected means every day.</p>
      </fieldset>
      <div className="sm:col-span-2">
        <label className="label" htmlFor="t-source">Source of this rate</label>
        <input id="t-source" required minLength={5} className="input"
          placeholder="Tariff order name and date, as published by your regulator" value={form.source} onChange={set("source")} />
      </div>
      <div className="sm:col-span-4 flex items-center gap-3">
        <button type="submit" className="btn-primary">Save tariff band</button>
        <ErrorBanner error={error} />
        <SuccessBanner>{notice}</SuccessBanner>
      </div>
    </form>
  );
}

function FactorForm({ onCreated }) {
  const [form, setForm] = useState({ value: "", unit: "kgCO2e/kWh", effective_from: todayInputValue(), effective_to: "",
    version_or_year: "", source: "" });
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  async function submit(event) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    try {
      await energyApi.createFactor({ ...form, value: String(form.value), effective_to: form.effective_to || null });
      setNotice("Emission factor saved.");
      onCreated();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4" onSubmit={submit}>
      <div><label className="label" htmlFor="f-value">Factor value</label>
        <input id="f-value" type="number" step="0.000001" min="0" required className="input" value={form.value} onChange={set("value")} /></div>
      <div><label className="label" htmlFor="f-unit">Unit</label>
        <input id="f-unit" required className="input" value={form.unit} onChange={set("unit")} /></div>
      <div><label className="label" htmlFor="f-from">Effective from</label>
        <input id="f-from" type="date" required className="input" value={form.effective_from} onChange={set("effective_from")} /></div>
      <div><label className="label" htmlFor="f-to">Effective to (optional)</label>
        <input id="f-to" type="date" className="input" value={form.effective_to} onChange={set("effective_to")} /></div>
      <div><label className="label" htmlFor="f-version">Version or year</label>
        <input id="f-version" required className="input" value={form.version_or_year} onChange={set("version_or_year")} /></div>
      <div className="sm:col-span-3"><label className="label" htmlFor="f-source">Source</label>
        <input id="f-source" required minLength={5} className="input" placeholder="Publisher and document, as cited" value={form.source} onChange={set("source")} /></div>
      <div className="sm:col-span-4 flex items-center gap-3">
        <button type="submit" className="btn-primary">Save emission factor</button>
        <ErrorBanner error={error} />
        <SuccessBanner>{notice}</SuccessBanner>
      </div>
    </form>
  );
}

export default function Energy() {
  const { can } = useAuth();
  const tariffs = useAsync(() => energyApi.tariffs(), []);
  const factors = useAsync(() => energyApi.factors(), []);
  const canWrite = can("energy:write");
  const noConfig = tariffs.data?.length === 0 || factors.data?.length === 0;

  return (
    <>
      <PageHeader
        title="Tariffs and emission factors"
        description="Enter the values from your own tariff order and emission-factor source. LabMeter does not ship official values."
      />
      {noConfig && (
        <div className="mb-6 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          Cost and emissions estimates stay hidden until at least one tariff band and one emission factor are entered.
        </div>
      )}
      {!canWrite && <p className="mb-4 text-sm text-slate-500">Read-only for your role.</p>}

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="card space-y-4">
          <h2 className="text-sm font-semibold text-slate-700">Tariff bands</h2>
          <p className="text-xs text-slate-500">
            Each band covers local hours on chosen weekdays and must not overlap another band. Hours that no band covers are not priced.
          </p>
          {canWrite && <TariffForm onCreated={tariffs.reload} />}
          {tariffs.loading && <LoadingState />}
          <ErrorBanner error={tariffs.error} onRetry={tariffs.reload} />
          {tariffs.data?.length === 0 && <EmptyState title="No tariff bands yet" />}
          {tariffs.data?.length > 0 && (
            <table className="min-w-full text-sm">
              <thead><tr className="text-left text-xs uppercase text-slate-500"><th scope="col" className="py-1 pr-2">Band</th><th scope="col" className="py-1 pr-2">Rate</th><th scope="col" className="py-1 pr-2">Hours</th><th scope="col" className="py-1 pr-2">Days</th><th scope="col" className="py-1">Source</th></tr></thead>
              <tbody>
                {tariffs.data.map((t) => (
                  <tr key={t.id} className="border-t border-slate-100 align-top">
                    <td className="py-1 pr-2">{t.time_band ?? "—"}</td>
                    <td className="py-1 pr-2 whitespace-nowrap">{t.rate_per_kwh} {t.currency}/kWh</td>
                    <td className="py-1 pr-2 whitespace-nowrap">{t.start_hour}:00–{t.end_hour}:00</td>
                    <td className="py-1 pr-2">{t.weekdays ? t.weekdays.split(",").map((d) => DAY_LABELS[Number(d)]).join(" ") : "All"}</td>
                    <td className="py-1 text-xs text-slate-600">{t.effective_from}{t.effective_to ? ` to ${t.effective_to}` : " onward"}<br />{t.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="card space-y-4">
          <h2 className="text-sm font-semibold text-slate-700">Emission factors</h2>
          <p className="text-xs text-slate-500">
            A factor applies to each day within its dates. Factors must not overlap. The source and year are shown with every estimate.
          </p>
          {canWrite && <FactorForm onCreated={factors.reload} />}
          {factors.loading && <LoadingState />}
          <ErrorBanner error={factors.error} onRetry={factors.reload} />
          {factors.data?.length === 0 && <EmptyState title="No emission factors yet" />}
          {factors.data?.length > 0 && (
            <table className="min-w-full text-sm">
              <thead><tr className="text-left text-xs uppercase text-slate-500"><th scope="col" className="py-1 pr-2">Value</th><th scope="col" className="py-1 pr-2">Version</th><th scope="col" className="py-1">Source and dates</th></tr></thead>
              <tbody>
                {factors.data.map((f) => (
                  <tr key={f.id} className="border-t border-slate-100 align-top">
                    <td className="py-1 pr-2 whitespace-nowrap">{f.value} {f.unit}</td>
                    <td className="py-1 pr-2">{f.version_or_year}</td>
                    <td className="py-1 text-xs text-slate-600">{f.effective_from}{f.effective_to ? ` to ${f.effective_to}` : " onward"}<br />{f.source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </>
  );
}
