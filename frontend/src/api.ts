import type {
  ChainResponseA,
  ExternalHostResponse,
  Rule,
  RuleCreateRequest,
  SandboxCreateRequest,
  SandboxDetailResponse,
  SandboxSummary,
  ServiceInfo,
} from "./types";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, options);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${text}`);
  }
  if (response.status === 204) return null as T;
  return (await response.json()) as T;
}

export function fetchChain(sandboxId?: string | null): Promise<ChainResponseA> {
  const headers: Record<string, string> = sandboxId ? { "X-Sandbox-ID": sandboxId } : {};
  return request<ChainResponseA>("/api/chain", { headers });
}

export function listExternals(): Promise<ExternalHostResponse[]> {
  return request<ExternalHostResponse[]>("/mocks/externals");
}

export function listRules(sandboxId?: string): Promise<Rule[]> {
  const query = sandboxId ? `?sandbox_id=${encodeURIComponent(sandboxId)}` : "";
  return request<Rule[]>(`/mocks/rules${query}`);
}

export function createRule(rule: RuleCreateRequest): Promise<Rule> {
  return request<Rule>("/mocks/rules", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(rule),
  });
}

export function deleteRule(id: string): Promise<null> {
  return request<null>(`/mocks/rules/${id}`, { method: "DELETE" });
}

export function toggleRule(id: string): Promise<Rule> {
  return request<Rule>(`/mocks/rules/${id}/toggle`, { method: "POST" });
}

export function listServices(): Promise<ServiceInfo[]> {
  return request<ServiceInfo[]>("/sandboxes-api/services");
}

export function listSandboxes(): Promise<SandboxSummary[]> {
  return request<SandboxSummary[]>("/sandboxes-api/sandboxes");
}

export function createSandbox(sandbox: SandboxCreateRequest): Promise<SandboxDetailResponse> {
  return request<SandboxDetailResponse>("/sandboxes-api/sandboxes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sandbox),
  });
}

export function deleteSandbox(name: string): Promise<null> {
  return request<null>(`/sandboxes-api/sandboxes/${name}`, { method: "DELETE" });
}
