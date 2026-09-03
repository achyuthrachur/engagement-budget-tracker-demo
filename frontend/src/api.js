export async function api(path, options = {}) {
  const init = { method: options.method || "GET", headers: { ...(options.headers || {}) } };
  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  const payload = await response.json().catch(() => ({ data: null, error: { message: "Invalid server response" } }));
  if (!response.ok) {
    const error = new Error(payload.error?.message || "Request failed");
    error.details = payload.error || {};
    throw error;
  }
  return payload.data;
}
