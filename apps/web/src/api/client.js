const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";
const ACCESS_TOKEN_KEY = "bloodlink.accessToken";
const REFRESH_TOKEN_KEY = "bloodlink.refreshToken";
class ApiError extends Error {
  status;
  code;
  details;
  requestId;
  constructor(status, code, message, details = [], requestId) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
  /** Field -> message map for form rendering. */
  get fieldErrors() {
    const map = {};
    for (const detail of this.details) {
      if (detail.field) map[detail.field] = detail.message ?? "Invalid value";
    }
    return map;
  }
}
const session = {
  accessToken: () => localStorage.getItem(ACCESS_TOKEN_KEY),
  refreshToken: () => localStorage.getItem(REFRESH_TOKEN_KEY),
  save(payload) {
    localStorage.setItem(ACCESS_TOKEN_KEY, payload.accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, payload.refreshToken);
  },
  clear() {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  }
};
function buildUrl(path, query) {
  const url = `${BASE_URL}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === void 0 || value === null || value === "") continue;
    params.append(key, String(value));
  }
  const serialised = params.toString();
  return serialised ? `${url}?${serialised}` : url;
}
const expiryListeners = /* @__PURE__ */ new Set();
function onSessionExpired(listener) {
  expiryListeners.add(listener);
  return () => expiryListeners.delete(listener);
}
function notifySessionExpired() {
  for (const listener of [...expiryListeners]) {
    try {
      listener();
    } catch {
    }
  }
}
let refreshInFlight = null;
async function attemptRefresh() {
  const refreshToken = session.refreshToken();
  if (!refreshToken) return false;
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${BASE_URL}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refreshToken })
        });
        if (!response.ok) return false;
        const envelope = await response.json();
        if (envelope.error || !envelope.data) return false;
        session.save(envelope.data);
        return true;
      } catch {
        return false;
      } finally {
        window.setTimeout(() => {
          refreshInFlight = null;
        }, 0);
      }
    })();
  }
  return refreshInFlight;
}
async function apiRequest(path, options = {}) {
  const { method = "GET", body, query, retry = true } = options;
  const headers = { Accept: "application/json" };
  if (body !== void 0) headers["Content-Type"] = "application/json";
  const token = session.accessToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === void 0 ? void 0 : JSON.stringify(body)
    });
  } catch (error) {
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the BloodLink API. Is it running?", [], null);
  }
  if (response.status === 204) {
    return void 0;
  }
  let envelope = null;
  try {
    envelope = await response.json();
  } catch {
    envelope = null;
  }
  // A 401 means the server no longer accepts this token (expired, revoked, or the
  // database was reset). Try one silent refresh; if that is impossible or fails,
  // end the local session and tell the app so it can show the sign-in screen
  // instead of polling forever with a dead token.
  if (response.status === 401 && retry && !path.startsWith("/auth/")) {
    if (session.refreshToken() && (await attemptRefresh())) {
      return apiRequest(path, { ...options, retry: false });
    }
    session.clear();
    notifySessionExpired();
  }
  if (!response.ok || !envelope || envelope.error) {
    const code = envelope?.error?.code ?? `HTTP_${response.status}`;
    const message = envelope?.error?.message ?? response.statusText ?? "Request failed";
    const details = envelope?.error?.details ?? [];
    throw new ApiError(response.status, code, message, details, envelope?.meta?.requestId ?? null);
  }
  return envelope.data;
}
const api = {
  get: (path, query) => apiRequest(path, { query }),
  post: (path, body) => apiRequest(path, { method: "POST", body }),
  patch: (path, body) => apiRequest(path, { method: "PATCH", body }),
  put: (path, body) => apiRequest(path, { method: "PUT", body }),
  delete: (path) => apiRequest(path, { method: "DELETE" })
};
export {
  ApiError,
  api,
  apiRequest,
  onSessionExpired,
  session
};
