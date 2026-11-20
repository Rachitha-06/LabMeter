/** Display helpers. Energy values arrive as strings and are converted only for display. */

export function kwhNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

export function formatKwh(value, digits = 2) {
  const n = kwhNumber(value);
  return `${n.toLocaleString(undefined, { maximumFractionDigits: digits })} kWh`;
}

export function formatCount(value) {
  return Number(value ?? 0).toLocaleString();
}

/** Convert a value from <input type="datetime-local"> (browser time) to an ISO string in UTC. */
export function localInputToIso(value) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toISOString();
}

/** Start of the day for a <input type="date"> value, in browser time, as UTC ISO. */
export function dateInputStartIso(value) {
  if (!value) return null;
  return new Date(`${value}T00:00:00`).toISOString();
}

/** Start of the day after a date input value, so the end date is inclusive. */
export function dateInputEndIso(value) {
  if (!value) return null;
  const next = new Date(`${value}T00:00:00`);
  next.setDate(next.getDate() + 1);
  return next.toISOString();
}

/** Format an ISO timestamp in a specific IANA timezone, for example a laboratory's timezone. */
export function formatInZone(iso, timeZone) {
  if (!iso) return "";
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone,
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZoneName: "short",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

/** The calendar day after an ISO date string (YYYY-MM-DD). */
export function dayAfter(isoDay) {
  const d = new Date(`${isoDay}T00:00:00`);
  d.setDate(d.getDate() + 1);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function daysAgoInputValue(days) {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function todayInputValue() {
  return daysAgoInputValue(0);
}

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
