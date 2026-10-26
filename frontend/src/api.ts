let token = sessionStorage.getItem("supportflow-token") || "";
export function setToken(value: string) {
  token = value;
  if (value) sessionStorage.setItem("supportflow-token", value);
  else sessionStorage.removeItem("supportflow-token");
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: "服务暂时不可用" }));
    if (response.status === 401 && path !== "/auth/login")
      window.dispatchEvent(new Event("supportflow-expired"));
    throw new Error(
      typeof data.detail === "string" ? data.detail : "请检查表单内容后重试",
    );
  }
  return response.json();
}

export async function streamChat(
  conversationId: string,
  message: string,
  requestId: string,
  onEvent: (event: string, data: unknown) => void,
) {
  const response = await fetch(
    `/api/conversations/${conversationId}/messages/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ message, request_id: requestId }),
    },
  );
  if (!response.ok) {
    const data = await response.json();
    throw new Error(data.detail || "分析请求失败");
  }
  if (!response.body) throw new Error("浏览器不支持流式响应");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let name = "message",
        data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event: ")) name = line.slice(7);
        if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data) {
        onEvent(name, JSON.parse(data));
        if (name === "done" || name === "error") completed = true;
      }
    }
    if (done) break;
  }
  if (!completed) throw new Error("连接中断，请刷新会话历史确认结果");
}
