import { describe, expect, it } from "vitest";
import {
  dateInputEndIso, dateInputStartIso, formatCount, formatKwh, kwhNumber, localInputToIso,
} from "./format.js";

describe("energy formatting", () => {
  it("reads decimal strings without float surprises", () => {
    expect(kwhNumber("1.2500")).toBe(1.25);
    expect(kwhNumber("not a number")).toBe(0);
  });

  it("formats kWh with a unit and limited digits", () => {
    expect(formatKwh("1.2500", 4)).toMatch(/^1\.25 kWh$/);
    expect(formatKwh("1234.5")).toMatch(/kWh$/);
  });

  it("formats counts", () => {
    expect(formatCount(6469)).toMatch(/6.469|6,469/);
    expect(formatCount(undefined)).toBe("0");
  });
});

describe("date and time conversion", () => {
  it("converts a datetime-local value to a UTC ISO string", () => {
    const iso = localInputToIso("2026-10-01T08:00");
    expect(iso.endsWith("Z")).toBe(true);
    expect(new Date(iso).getTime()).toBe(new Date("2026-10-01T08:00").getTime());
  });

  it("returns null for empty or invalid datetime input", () => {
    expect(localInputToIso("")).toBeNull();
    expect(localInputToIso("not a date")).toBeNull();
  });

  it("makes the end date inclusive by moving to the next day's start", () => {
    const start = new Date(dateInputStartIso("2026-10-01")).getTime();
    const end = new Date(dateInputEndIso("2026-10-01")).getTime();
    expect(end - start).toBe(24 * 60 * 60 * 1000);
  });
});
