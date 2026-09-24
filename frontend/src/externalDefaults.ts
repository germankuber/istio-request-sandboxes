import type { ExternalHostId, HttpMethod } from "./types";

export interface ExternalDefaults {
  method: HttpMethod;
  path: string;
  status: number;
  body: string;
}

export const EXTERNAL_DEFAULTS: Record<ExternalHostId, ExternalDefaults> = {
  "external-payments": {
    method: "POST",
    path: "/charge",
    status: 402,
    body: '{\n  "error": "card_declined"\n}',
  },
  "external-weather": {
    method: "GET",
    path: "/weather",
    status: 200,
    body: '{\n  "city": "Buenos Aires",\n  "temp_c": -40,\n  "condition": "snow",\n  "provider": "mock"\n}',
  },
};

export const DEFAULT_EXTERNAL_HOST_ID: ExternalHostId = "external-payments";

export function defaultsForHost(host: string): ExternalDefaults {
  return EXTERNAL_DEFAULTS[host as ExternalHostId] ?? EXTERNAL_DEFAULTS[DEFAULT_EXTERNAL_HOST_ID];
}
