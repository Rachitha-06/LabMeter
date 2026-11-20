import { Link } from "react-router-dom";
import { energy as energyApi } from "../api/endpoints.js";
import { EmptyState, ErrorBanner, LoadingState } from "./States.jsx";
import { useAsync } from "../hooks/useAsync.js";
import { formatCount } from "../utils/format.js";

function money(value, currency) {
  const n = Number(value);
  const text = n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency ? `${text} ${currency}` : text;
}

/** Cost and emissions estimates for the dashboard period. Shows guidance when nothing is configured yet. */
export default function EstimateCards({ start, end, labId }) {
  const params = { start, end, granularity: "day" };
  if (labId) params.lab_id = labId;
  const estimate = useAsync(() => (start && end ? energyApi.estimate(params) : Promise.resolve(null)),
    [start, end, labId]);

  if (estimate.loading) return <LoadingState label="Estimating cost and emissions…" />;
  if (estimate.error) {
    if (estimate.error.code === "no_tariff" || estimate.error.code === "no_emission_factor") {
      return (
        <EmptyState title="Cost and emissions are not estimated yet">
          {estimate.error.message}{" "}
          <Link className="text-emerald-800 underline" to="/energy">Open tariffs and factors</Link>
        </EmptyState>
      );
    }
    return <ErrorBanner error={estimate.error} onRetry={estimate.reload} />;
  }
  const total = estimate.data?.total;
  if (!total) return null;
  const currency = estimate.data.currency;
  const unit = estimate.data.emission_unit;

  return (
    <section className="mb-6">
      <p className="mb-2 text-xs text-slate-500">
        Estimates from the configured tariff and emission factor. They are not measured costs or emissions, and taxes and
        fixed charges are not included.
      </p>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="card">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Estimated cost</p>
          <p className="mt-1 text-2xl font-semibold text-slate-900">
            {currency ? money(total.estimated_cost, currency) : "Mixed currencies"}
          </p>
          <p className="mt-1 text-xs text-slate-500">{formatCount(Number(total.kwh_with_tariff))} kWh priced</p>
        </div>
        <div className="card">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Estimated emissions</p>
          <p className="mt-1 text-2xl font-semibold text-slate-900">
            {unit ? `${Number(total.estimated_emissions).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${unit.replace("/kWh", "")}` : "Mixed units"}
          </p>
          <p className="mt-1 text-xs text-slate-500">{formatCount(Number(total.kwh_without_factor))} kWh without a factor</p>
        </div>
        {Number(total.kwh_without_tariff) > 0 && (
          <div className="card sm:col-span-2">
            <p className="text-sm text-amber-900">
              {Number(total.kwh_without_tariff).toLocaleString(undefined, { maximumFractionDigits: 2 })} kWh fall outside every
              configured tariff band and are not priced. Add the missing band to complete the estimate.
            </p>
          </div>
        )}
      </div>
    </section>
  );
}
