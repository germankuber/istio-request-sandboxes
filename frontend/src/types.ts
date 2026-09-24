export type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

export const METHODS: HttpMethod[] = ["GET", "POST", "PUT", "DELETE"];

export type ExternalHostId = "external-payments" | "external-weather";

export interface ExternalHostResponse {
  id: ExternalHostId;
  label: string;
}

export type RuleBody = Record<string, unknown> | unknown[] | string | number | boolean | null;

export interface RuleCreateRequest {
  sandbox_id: string;
  host: ExternalHostId;
  method: HttpMethod;
  path: string;
  status: number;
  headers: Record<string, string>;
  body: RuleBody;
  delay_ms: number;
  enabled: boolean;
}

export interface Rule {
  id: string;
  sandbox_id: string;
  host: ExternalHostId;
  method: string;
  path: string;
  status: number;
  headers: Record<string, string>;
  body: RuleBody;
  delay_ms: number;
  enabled: boolean;
}

export type SandboxPhase = "Pending" | "Ready" | "Failed" | "Deleting";

export const DELETING_PHASE: SandboxPhase = "Deleting";
export const TRANSIENT_PHASES: SandboxPhase[] = ["Pending", DELETING_PHASE];

export interface ServiceInfo {
  name: string;
  uses_db: boolean;
}

export interface SandboxSummary {
  name: string;
  phase: SandboxPhase;
  message: string;
  services: string[];
  mocks_count: number;
  created_at: string | null;
}

export interface SandboxDetailResponse {
  name: string;
  spec: Record<string, unknown>;
  status: Record<string, unknown>;
}

export interface EnvVarRequest {
  name: string;
  value: string;
}

export interface ServiceCreateRequest {
  name: string;
  image: string | null;
  env: EnvVarRequest[];
  use_migrated_db: boolean;
}

export interface MockCreateRequest {
  host: string;
  method: HttpMethod;
  path: string;
  status: number;
  body: RuleBody;
  enabled: boolean;
}

export interface SandboxCreateRequest {
  name: string;
  services: ServiceCreateRequest[];
  mocks: MockCreateRequest[];
}

export interface ChainErrorNode {
  error: string;
  detail: string;
}

export interface ExternalResultOk {
  http_status: number;
  mocked: boolean;
  data: unknown;
}

export interface ExternalResultError {
  error: string;
  detail: string;
  mocked: boolean;
}

export type ExternalResult = ExternalResultOk | ExternalResultError;

export interface ProductLegacy {
  id: number;
  name: string;
  price_cents: number;
  stock: number;
}

export interface ProductSplit {
  id: number;
  brand: string;
  model: string;
  price_cents: number;
  stock: number;
}

export type Product = ProductLegacy | ProductSplit;

export interface ChainNodeC {
  service: "C";
  version: string;
  schema: string;
  products: Product[];
}

export interface ChainNodeD {
  service: "D";
  version: string;
  external: {
    payments: ExternalResult;
    weather: ExternalResult;
  };
}

export interface LowStockItem {
  id: number;
  name: string;
  stock: number;
}

export interface ChainNodeE {
  service: "E";
  version: string;
  product_count: number;
  inventory_value_cents: number;
  low_stock: LowStockItem[];
}

export type ChainNode = ChainNodeC | ChainNodeD | ChainNodeE | ChainErrorNode;

export interface ChainDownstream {
  c: ChainNode;
  d: ChainNode;
  e: ChainNode;
}

export interface ChainResponseB {
  service: "B";
  version: string;
  sandbox_id: string | null;
  downstream: ChainDownstream;
}

export interface ChainResponseA {
  service: "A";
  version: string;
  sandbox_id: string | null;
  downstream: ChainResponseB;
}

export interface ChainLocalError {
  error: string;
}

export type ChainResult = ChainResponseA | ChainLocalError;

export function isChainErrorNode(node: ChainNode | null | undefined): node is ChainErrorNode {
  return Boolean(node) && "error" in (node as object);
}

export function isChainResponse(result: ChainResult | null | undefined): result is ChainResponseA {
  return result !== null && result !== undefined && "downstream" in result;
}
