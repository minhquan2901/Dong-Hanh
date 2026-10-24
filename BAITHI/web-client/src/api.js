const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim().replace(/\/+$/, "");
const API_BASE = configuredBase || (import.meta.env.PROD ? null : "");

export async function api(path, { token, ...options } = {}) {
  if (API_BASE === null) {
    throw new Error("Frontend chưa được cấu hình API. Hãy đặt VITE_API_BASE_URL trỏ đến backend Render rồi deploy lại.");
  }

  const headers = new Headers(options.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    throw new Error("Không kết nối được máy chủ. Vui lòng thử lại sau.");
  }

  const payload = await response.json().catch(() => null);
  const data = payload && typeof payload === "object" ? payload : {};
  if (!response.ok) {
    const suggestions = response.headers.get("X-Username-Suggestions");
    const suggestionText = suggestions ? ` Gợi ý tên: ${suggestions.split(",").join(", ")}.` : "";
    const diagnostic = response.status >= 500
      ? ` (HTTP ${response.status} tại ${options.method || "GET"} ${path})`
      : "";
    if (response.status === 401 && token) {
      localStorage.removeItem("study_sync_user");
      localStorage.removeItem("study_sync_session_token");
      window.dispatchEvent(new Event("studysync-session-expired"));
    }
    throw new Error(`${data.detail || data.message || "Yêu cầu thất bại."}${suggestionText}${diagnostic}`);
  }
  return data;
}

export const apiBaseUrl = API_BASE;
