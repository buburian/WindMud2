// 呼叫編輯器的後端（mud/builder/server.py）。出錯時丟 Error，訊息是後端給的中文。

async function request(method, url, body) {
  const options = { method };
  if (body !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error("連不到編輯器的伺服器，請確認它還開著");
  }
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.error || `伺服器回傳 ${response.status}`);
  return result;
}

const areaUrl = (file) => `/api/areas/${encodeURIComponent(file)}`;

export const listAreas = () => request("GET", "/api/areas");
export const createArea = (file, title, area_number) => request("POST", "/api/areas", { file, title, area_number });
export const readArea = (file) => request("GET", areaUrl(file));
export const saveArea = (file, data) => request("PUT", areaUrl(file), data);
export const checkArea = (file, data) => request("POST", `${areaUrl(file)}/check`, data);
