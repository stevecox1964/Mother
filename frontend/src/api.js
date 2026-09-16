// Same relative /api boundary as BookMarkManager's service layer.
export async function api(path, method = "GET", data) {
  const response = await fetch("/api" + path, {
    method,
    headers: data === undefined ? {} : { "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Request failed");
  return body;
}

export const projectApi = (projectId) => (path, method, data) =>
  api(
    path +
      (path.includes("?") ? "&" : "?") +
      new URLSearchParams({ project_id: projectId }),
    method,
    data,
  );
