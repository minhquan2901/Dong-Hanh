const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, "");
const API_BASE = configuredBase || (import.meta.env.PROD ? null : "");
const requestCounts = new Map();
const API_CACHE_PREFIX = "study_sync_api_cache_v1:";
const API_CACHE_TTL_MS = 5 * 60 * 1000;
const CACHEABLE_GET_PATHS = new Set([
  "/api/dashboard/student",
  "/api/dashboard/parent",
  "/api/schedule/slots",
]);

function apiCacheKey(path) {
  let username = "anonymous";
  try {
    const user = JSON.parse(localStorage.getItem("study_sync_user") || "null");
    if (user?.username) username = String(user.username).trim().toLowerCase();
  } catch (error) {
    console.warn("Không xác định được tài khoản cho bộ nhớ đệm StudySync:", error);
  }
  return `${API_CACHE_PREFIX}${encodeURIComponent(username)}:${encodeURIComponent(path)}`;
}

function readApiCache(path) {
  try {
    const value = sessionStorage.getItem(apiCacheKey(path));
    if (value === null) return null;
    const cached = JSON.parse(value);
    if (
      !cached
      || typeof cached !== "object"
      || !cached.data
      || typeof cached.data !== "object"
      || !Number.isFinite(cached.storedAt)
      || Date.now() - cached.storedAt >= API_CACHE_TTL_MS
    ) {
      sessionStorage.removeItem(apiCacheKey(path));
      return null;
    }
    return cached.data;
  } catch (error) {
    console.warn("Không đọc được bộ nhớ đệm StudySync:", error);
    return null;
  }
}

function writeApiCache(path, data) {
  try {
    sessionStorage.setItem(apiCacheKey(path), JSON.stringify({ data, storedAt: Date.now() }));
  } catch (error) {
    console.warn("Không lưu được bộ nhớ đệm StudySync:", error);
  }
}

export function clearApiCache() {
  try {
    for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = sessionStorage.key(index);
      if (key?.startsWith(API_CACHE_PREFIX)) sessionStorage.removeItem(key);
    }
  } catch (error) {
    console.error("Không xóa được bộ nhớ đệm StudySync:", error);
  }
}

function recordRequestTiming(path, method, durationMs, headerMs, status) {
  const endpoint = path.split("?")[0];
  const requestKey = `${method} ${endpoint}`;
  const requestNumber = (requestCounts.get(requestKey) || 0) + 1;
  requestCounts.set(requestKey, requestNumber);

  const measurement = {
    request: `${method} ${endpoint}`,
    requestNumber,
    headersMs: Math.round(headerMs),
    totalMs: Math.round(durationMs),
    status,
  };
  if (requestNumber === 1 || durationMs >= 1000) {
    const log = durationMs >= 1000 ? console.warn : console.info;
    log("[StudySync API timing]", measurement);
  }
}

export async function api(path, { token, forceRefresh = false, ...options } = {}) {
  if (API_BASE === null) {
    throw new Error("Frontend chưa được cấu hình API. Hãy đặt VITE_API_BASE_URL trỏ đến backend Render rồi deploy lại.");
  }

  const method = String(options.method || "GET").toUpperCase();
  const endpoint = path.split("?")[0];
  if (method === "GET" && CACHEABLE_GET_PATHS.has(endpoint) && !forceRefresh) {
    const cached = readApiCache(path);
    if (cached !== null) return cached;
  }

  const headers = new Headers(options.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response;
  const startedAt = performance.now();
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (error) {
    recordRequestTiming(path, method, performance.now() - startedAt, performance.now() - startedAt, "network-error");
    console.error("Không kết nối được API StudySync:", error);
    throw new Error("Không kết nối được máy chủ. Vui lòng thử lại sau.");
  }

  const headersAt = performance.now();
  const payload = await response.json().catch(() => null);
  recordRequestTiming(path, method, performance.now() - startedAt, headersAt - startedAt, response.status);
  const data = payload && typeof payload === "object" ? payload : {};
  if (!response.ok) {
    const suggestions = response.headers.get("X-Username-Suggestions");
    const suggestionText = suggestions ? ` Gợi ý tên: ${suggestions.split(",").join(", ")}.` : "";
    const diagnostic = response.status >= 500
      ? ` (HTTP ${response.status} tại ${method} ${path})`
      : "";
    if (response.status === 401 && token) {
      localStorage.removeItem("study_sync_user");
      localStorage.removeItem("study_sync_session_token");
      window.dispatchEvent(new Event("studysync-session-expired"));
    }
    throw new Error(`${data.detail || data.message || "Yêu cầu thất bại."}${suggestionText}${diagnostic}`);
  }
  if (method === "GET" && CACHEABLE_GET_PATHS.has(endpoint)) {
    writeApiCache(path, data);
  } else if (method !== "GET") {
    clearApiCache();
  }
  return data;
}

export const apiBaseUrl = API_BASE;
