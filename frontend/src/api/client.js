/**
 * Thin wrapper around fetch. Every API failure, including a network failure,
 * becomes an ApiError with the same code/message/details shape the backend returns.
 *
 * The session token lives in sessionStorage: it is cleared when the browser tab closes, and it is
 * never placed in the URL or in localStorage. An httpOnly cookie would be stronger against script
 * theft; that is listed as future hardening in the README.
 */
export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
const TOKEN_KEY = "labmeter.token";

let unauthorizedHandler = null;

export class ApiError extends Error {
  constructor(status, code, message, details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

export function getToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage can be unavailable (for example, in some private browsing modes). The session then lasts one page.
  }
}

export async function api(path, { method = "GET", body, form } = {}) {
  const init = { method, headers: {} };
  const token = getToken();
  if (token) init.headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  if (form !== undefined) {
    init.body = form; // FormData: the browser sets the multipart boundary itself
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the LabMeter API. Is the server running?");
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const error = payload?.error;
    // A rejected session ends the signed-in state. Wrong passwords on the login route do not.
    if (response.status === 401 && token && !path.startsWith("/auth/login") && unauthorizedHandler) {
      unauthorizedHandler();
    }
    throw new ApiError(
      response.status,
      error?.code ?? "http_error",
      error?.message ?? `Request failed with status ${response.status}`,
      error?.details ?? null,
    );
  }
  return payload;
}
