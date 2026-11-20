import { api } from "./client.js";

export const health = () => api("/health");

export const labs = {
  list: (includeArchived = false) => api(`/labs${includeArchived ? "?include_archived=true" : ""}`),
  archive: (id) => api(`/labs/${id}/archive`, { method: "POST" }),
  restore: (id) => api(`/labs/${id}/restore`, { method: "POST" }),
  dataRange: (id) => api(`/labs/${id}/data-range`),
  get: (id) => api(`/labs/${id}`),
  create: (body) => api("/labs", { method: "POST", body }),
  update: (id, body) => api(`/labs/${id}`, { method: "PATCH", body }),
  equipment: (id) => api(`/labs/${id}/equipment`),
  addEquipment: (id, body) => api(`/labs/${id}/equipment`, { method: "POST", body }),
  schedules: (id) => api(`/labs/${id}/schedules`),
  addSchedule: (id, body) => api(`/labs/${id}/schedules`, { method: "POST", body }),
};

export const readings = {
  list: (params) => api(`/readings?${new URLSearchParams(params)}`),
  create: (body) => api("/readings", { method: "POST", body }),
  correct: (id, body) => api(`/readings/${id}`, { method: "PATCH", body }),
  revisions: (id) => api(`/readings/${id}/revisions`),
};

export const imports = {
  upload: (file, { dryRun, intervalMinutes }) => {
    const form = new FormData();
    form.append("file", file);
    const params = new URLSearchParams({
      dry_run: String(dryRun),
      interval_minutes: String(intervalMinutes),
    });
    return api(`/imports/readings?${params}`, { method: "POST", form });
  },
};

export const forecasts = {
  list: (params) => api(`/forecasts?${new URLSearchParams(params)}`),
  get: (id) => api(`/forecasts/${id}`),
  create: (body) => api("/forecasts", { method: "POST", body }),
  evaluation: (labId) => api(`/forecasts/evaluation?${new URLSearchParams({ lab_id: labId })}`),
};

export const models = {
  comparison: () => api("/models/comparison"),
  status: () => api("/models/status"),
};

export const alerts = {
  list: (params) => api(`/alerts?${new URLSearchParams(params)}`),
  get: (id) => api(`/alerts/${id}`),
  detect: (body) => api("/alerts/detect", { method: "POST", body }),
  update: (id, body) => api(`/alerts/${id}`, { method: "PATCH", body }),
  count: (params) => api(`/alerts/count?${new URLSearchParams(params)}`),
  comment: (id, comment) => api(`/alerts/${id}/comments`, { method: "POST", body: { comment } }),
};

export const energy = {
  tariffs: () => api("/tariffs"),
  createTariff: (body) => api("/tariffs", { method: "POST", body }),
  factors: () => api("/emission-factors"),
  createFactor: (body) => api("/emission-factors", { method: "POST", body }),
  estimate: (params) => api(`/estimates/cost-emissions?${new URLSearchParams(params)}`),
};

export const analytics = {
  consumption: (params) => api(`/analytics/consumption?${new URLSearchParams(params)}`),
};

export const auth = {
  login: (body) => api("/auth/login", { method: "POST", body }),
  logout: () => api("/auth/logout", { method: "POST" }),
  me: () => api("/auth/me"),
  users: () => api("/auth/users"),
  createUser: (body) => api("/auth/users", { method: "POST", body }),
  updateUser: (id, body) => api(`/auth/users/${id}`, { method: "PATCH", body }),
};
