// Thin wrapper around fetch for the DevIntel API. Adds the auth token and turns
// error responses into thrown Errors with the server's message.
const TOKEN_KEY = "devintel.token";

export const tokenStore = {
  get() {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token) {
    try {
      if (token) localStorage.setItem(TOKEN_KEY, token);
      else localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* storage unavailable: session lasts until reload */
    }
  },
};

let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => {
  onUnauthorized = fn;
};

// Plain-language messages for the problems people actually hit.
const SERVER_DOWN =
  "Can't reach the DevIntel server. Check that the platform API is running (npm run dev in platform/server).";
const DB_DOWN =
  "The database is not responding. Check that the MongoDB service is running.";

function friendlyMessage(status, message = "") {
  if (
    /buffering timed out|MongoServerSelection|MongoNetworkError|27017/i.test(
      message,
    )
  )
    return DB_DOWN;
  if ([502, 503, 504].includes(status) || (status >= 500 && !message))
    return SERVER_DOWN;
  if (status === 403)
    return "You don't have permission to do that. Sign in as a manager.";
  return message || `Request failed (${status})`;
}

// Turns an AI service failure reason (from an analysis run) into plain words.
export function explainServiceError(reason = "") {
  if (/ECONNREFUSED|fetch failed|ENOTFOUND/i.test(reason))
    return "service not running";
  if (/timed out/i.test(reason)) return "service took too long to answer";
  return reason;
}

export async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  const token = tokenStore.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let res;
  try {
    res = await fetch(`/api${path}`, {
      method,
      headers,
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
    });
  } catch {
    const err = new Error(SERVER_DOWN);
    err.status = 0;
    throw err;
  }
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && path !== "/auth/login") onUnauthorized(data.error);
  if (!res.ok) {
    const err = new Error(friendlyMessage(res.status, data.error));
    err.status = res.status;
    throw err;
  }
  return data;
}
