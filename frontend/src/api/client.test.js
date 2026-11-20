import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, setToken, setUnauthorizedHandler } from "./client.js";

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns parsed JSON on success", async () => {
    fetch.mockResolvedValue({ ok: true, status: 200, json: async () => ({ status: "ok" }) });
    await expect(api("/health")).resolves.toEqual({ status: "ok" });
  });

  it("maps the backend error envelope to an ApiError with code, message and details", async () => {
    fetch.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({
        error: { code: "reading_conflict", message: "already stored", details: { existing_reading_id: 7 } },
      }),
    });
    const error = await api("/readings", { method: "POST", body: {} }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(409);
    expect(error.code).toBe("reading_conflict");
    expect(error.message).toBe("already stored");
    expect(error.details).toEqual({ existing_reading_id: 7 });
  });

  it("falls back to a generic message when the body is not the expected envelope", async () => {
    fetch.mockResolvedValue({ ok: false, status: 500, json: async () => { throw new SyntaxError(); } });
    const error = await api("/labs").catch((e) => e);
    expect(error.code).toBe("http_error");
    expect(error.message).toContain("500");
  });

  it("reports a network failure as a readable ApiError", async () => {
    fetch.mockRejectedValue(new TypeError("Failed to fetch"));
    const error = await api("/labs").catch((e) => e);
    expect(error.code).toBe("network_error");
    expect(error.message).toMatch(/Cannot reach/);
  });

  it("sends JSON bodies with the correct content type", async () => {
    fetch.mockResolvedValue({ ok: true, status: 201, json: async () => ({}) });
    await api("/labs", { method: "POST", body: { name: "Lab A" } });
    const [, init] = fetch.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ name: "Lab A" });
  });
});


describe("session token handling", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    sessionStorage.clear();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    setUnauthorizedHandler(null);
    setToken(null);
  });

  it("sends the stored token as a bearer header", async () => {
    setToken("token-123");
    fetch.mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    await api("/labs");
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe("Bearer token-123");
  });

  it("sends no header when signed out", async () => {
    fetch.mockResolvedValue({ ok: true, status: 200, json: async () => [] });
    await api("/labs");
    expect(fetch.mock.calls[0][1].headers.Authorization).toBeUndefined();
  });

  it("signs the user out when a protected request is rejected with 401", async () => {
    setToken("expired-token");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    fetch.mockResolvedValue({ ok: false, status: 401, json: async () => ({ error: { code: "unauthorized", message: "sign in" } }) });
    await expect(api("/labs")).rejects.toMatchObject({ status: 401 });
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not sign out when a wrong password is rejected on the login route", async () => {
    setToken("token-123");
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    fetch.mockResolvedValue({ ok: false, status: 401, json: async () => ({ error: { code: "invalid_credentials", message: "no" } }) });
    await expect(api("/auth/login", { method: "POST", body: {} })).rejects.toMatchObject({ code: "invalid_credentials" });
    expect(handler).not.toHaveBeenCalled();
  });
});
