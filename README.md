# Request-Scoped Sandboxes with Istio

One HTTP header routes a request to a modified version of a service, while everything else
stays on the shared baseline. **No routing logic in application code** — Istio decides, based
on `VirtualService`/`DestinationRule` objects a `Sandbox` custom resource generates on demand.

```mermaid
flowchart LR
    FE[frontend] -->|X-Sandbox-ID| A[service-a] --> B[service-b]

    B --> CB[service-c<br/>baseline]
    B -.-> CS[service-c<br/>sandbox]
    B --> EB[service-e<br/>baseline]
    B -.-> ES[service-e<br/>sandbox]
    B --> D[service-d<br/>no database]

    CB --> DB[(postgres<br/>baseline)]
    EB --> DB
    CS -.-> DS[(postgres<br/>sandbox<br/>migrated clone)]
    ES -.-> DS

    classDef sb stroke:#f59e0b,stroke-width:2px
    classDef ctl stroke:#64748b,stroke-dasharray:5
    class CS,ES,DS sb
    class D ctl
```

Solid lines are the default path; dashed lines activate only when the header matches a
ready sandbox.

| `X-Sandbox-ID` | service-c | service-e | service-d |
| --- | --- | --- | --- |
| absent | baseline | baseline | baseline |
| `test-123` | **sandbox** | **sandbox** | baseline |
| anything else | baseline | baseline | baseline |

`service-d` receives the header and still answers baseline — proof that only the services you
*choose* to sandbox get replaced.

`service-e` runs the identical image in both deployments; only `DATABASE_URL` differs. It
needs a sandbox deployment purely because the database it reads was migrated.

> **The sandbox boundary follows the data dependency graph, not the diff.**

Point the unmodified `service-e` at the migrated clone and it dies:

```
psycopg.errors.UndefinedColumn: column "name" does not exist
```

`service-c`/`service-e` pick their query shape from a `DB_SCHEMA` env var (`legacy` | `split`),
never from the routing version label — see [Gotchas](#gotchas).

## How the header travels

```mermaid
sequenceDiagram
    participant C as Client
    participant A as service-a
    participant I as Istio sidecar
    participant SB as service-c sandbox
    participant BL as service-c baseline

    C->>A: GET /chain<br/>X-Sandbox-ID: test-123
    Note over A: middleware stores id<br/>in a ContextVar
    A->>I: GET http://service-c/info<br/>(httpx hook re-injects header)
    Note over I: VirtualService matches<br/>x-sandbox-id == test-123
    I->>SB: routed to subset sandbox
    SB-->>C: {"version": "sandbox"}
    Note over BL: never sees this request
```

Both halves live in each service's `sandbox_propagation.py`. A `BaseHTTPMiddleware` reads the
inbound header into a `ContextVar` (reset in a `finally`, or ids leak across concurrent
requests); an httpx request hook reads that same `ContextVar` and re-injects the header on
every outbound call. A middleware alone only sees inbound traffic — the `ContextVar` is what
carries the value to the outbound client, so handlers just call `client.get(url)` with no
headers argument.

## Quick start

Requires [Colima](https://github.com/abiosoft/colima), `kubectl`, `istioctl`.

```bash
# 1. dedicated local cluster
colima start sandbox-poc --kubernetes --cpu 4 --memory 8 --disk 30

# 2. istio
istioctl install --context colima-sandbox-poc --set profile=demo -y
kubectl --context colima-sandbox-poc label namespace default istio-injection=enabled

# 3. images (Colima's k3s uses its own Docker daemon)
export DOCKER_HOST="unix://${HOME}/.colima/sandbox-poc/docker.sock"
for s in a b c d e; do docker build -t "service-${s}:latest" "./service-${s}"; done
docker build -t "external-payments:latest" ./external-payments
docker build -t "external-weather:latest" ./external-weather
docker build -t "mock-manager:latest" ./mock-manager
docker build -t "sandbox-controller:latest" ./sandbox-controller
docker build -t "sandbox-api:latest" ./sandbox-api
docker build -t frontend:latest ./frontend

# 4. deploy
kubectl --context colima-sandbox-poc apply \
  -f k8s/database/ -f k8s/deployments/ -f k8s/services/ -f k8s/istio/ \
  -f k8s/external/ -f k8s/mocking/ -f k8s/kiali/

# 4b. the sandbox controller: CRD first, then RBAC + the operator Deployment
kubectl --context colima-sandbox-poc apply -f k8s/sandbox-controller/

# 4c. the self-service sandbox API (RBAC + Deployment + Service)
kubectl --context colima-sandbox-poc apply -f k8s/sandbox-api/

# 5. databases
KUBECTL="kubectl --context colima-sandbox-poc" ./db/clone-and-migrate.sh

# 6. wait for 2/2 (app + sidecar; external-* and Kiali/Prometheus pods stay 1/1 —
# they are not mesh-injected), then forward the Istio ingress gateway,
# the single entry point (see Gotchas for why not a direct service port-forward)
kubectl --context colima-sandbox-poc get pods -w
kubectl --context colima-sandbox-poc -n istio-system port-forward svc/istio-ingressgateway 8081:80

# 7. create a sandbox
kubectl --context colima-sandbox-poc apply -f k8s/sandboxes/test-123.yaml
kubectl --context colima-sandbox-poc get sandboxes -w
```

> Quote the tag as `"service-${s}:latest"`. Unquoted, zsh reads `$s:latest` as a history
> modifier and silently builds `service-aatest` → `ImagePullBackOff`.

Other clusters: minikube needs `eval $(minikube docker-env)` before building; kind needs
`kind load docker-image …` after; containerd-based clusters need `k3s ctr images import`.

### Try it

Everything goes through the gateway port-forward from step 6:

```bash
curl -s http://localhost:8081/api/chain | jq '.downstream.downstream | map_values(.version)'
# { "c": "baseline", "d": "baseline", "e": "baseline" }

curl -s -H "X-Sandbox-ID: test-123" http://localhost:8081/api/chain \
  | jq '.downstream.downstream | map_values(.version)'
# { "c": "test-123", "d": "baseline", "e": "test-123" }

curl -s -H "X-Sandbox-ID: nope" http://localhost:8081/api/chain \
  | jq '.downstream.downstream | map_values(.version)'
# { "c": "baseline", "d": "baseline", "e": "baseline" }
```

The third case is the one that matters: the header propagates end to end, but no route
matches an unknown id, so baseline wins — **the application behaves identically in all three.**

The UI lives at http://localhost:8081/ (Sandboxes / Chain / Mocks tabs — see below).

## Using sandboxes

Sandboxes are never hand-written manifests. A team applies (or the UI creates) a `Sandbox`
custom resource naming the id and the services it touches; the `sandbox-controller` operator
generates the Deployments, the Istio routing, and the seed mock rules from it.

Why a controller instead of a hand-edited `VirtualService`: **Istio does not merge multiple
mesh `VirtualService` objects for the same host** — whichever one the control plane picks wins
outright, and the other's routes are silently ignored. A shared, hand-edited file is the only
way to add a route by hand, which makes every sandbox a merge conflict waiting to happen.

```yaml
apiVersion: sandbox.poc/v1
kind: Sandbox
metadata:
  name: test-123          # this becomes the X-Sandbox-ID / VERSION / subset name
spec:
  services:
    - name: service-c
      env:
        - name: DATABASE_URL
          value: postgresql://poc:poc@postgres-sandbox:5432/catalog
  mocks:
    - host: external-payments
      method: POST
      path: /charge
      status: 402
      body: { error: card_declined }
```

```bash
kubectl --context colima-sandbox-poc apply -f k8s/sandboxes/test-123.yaml
kubectl --context colima-sandbox-poc get sandboxes
# NAME       PHASE   MESSAGE                            AGE
# test-123   Ready   all sandboxed services available   12s

kubectl --context colima-sandbox-poc delete -f k8s/sandboxes/test-123.yaml
```

### Reconcile flow

```mermaid
flowchart TD
    CR[Sandbox CR<br/>test-123] -->|create/update/delete<br/>+ periodic timer| C[sandbox-controller<br/>kopf]
    C -->|clone baseline pod template<br/>image/env overrides| DEP[Deployment<br/>service-c-sb-test-123]
    C -->|subset per ready sandbox<br/>+ baseline| DR[DestinationRule<br/>service-c]
    C -->|exact header route per<br/>ready sandbox + baseline route| VS[VirtualService<br/>service-c]
    C -->|seed rules that don't<br/>already exist for this id| MM[mock-manager<br/>/rules?sandbox_id=]
    DEP -->|readiness gates routing| C

    classDef ctl stroke:#64748b,stroke-dasharray:5
    class C ctl
```

`sandbox-controller/` (hexagonal: `domain` → `application` → `infrastructure`) reconciles on
every `Sandbox` create/update/delete **and** on a `ROUTING_INTERVAL_SECONDS` timer, so a
deployment that becomes ready between events still gets routed. Key rules:

- A sandbox is only added to a service's routing once its Deployment reports
  `availableReplicas >= 1` — routing a not-yet-ready pod produces `503 no healthy upstream`.
- Deployments carry an `ownerReference` to their `Sandbox`, so deleting the CR
  garbage-collects them; the controller only has to clean up routing and mock rules.
- Generated `DestinationRule`/`VirtualService` objects are labeled
  `app.kubernetes.io/managed-by: sandbox-controller`, so the controller shares `k8s/istio/`
  with hand-written entries (`external-payments`/`external-weather`) without touching them.
- **Seed, don't override `enabled`.** The controller only `POST`s mock rules missing for
  `(sandbox_id, host, method, path)` — it never flips `enabled` on one that already exists, so
  a periodic re-reconcile can't silently re-enable a mock a team just disabled from the UI.

Two sandboxes can target the same service without conflict (each gets its own header-matched
route on the same `VirtualService`) — verified by the
`test_two_sandboxes_on_same_service_do_not_cross_talk` E2E test.

### Self-service UI

`sandbox-api/` (hexagonal FastAPI, same shape as `mock-manager/`) only reads and writes
`Sandbox` custom resources through the Python `kubernetes` client — it has no reconcile logic
of its own, so the CR stays the single source of truth and `sandbox-controller` still owns
every Deployment/routing/mock side effect.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/services` | Baseline services, flagged `uses_db` |
| `GET` | `/sandboxes` | Name, phase, message, service names, mock count, created time |
| `GET` | `/sandboxes/{name}` | Full CR `spec` + `status` |
| `POST` | `/sandboxes` | Creates the CR; `use_migrated_db: true` expands into the `DATABASE_URL`/`DB_SCHEMA=split` pair; `422` on an invalid DNS-1123 name, `409` if it exists |
| `DELETE` | `/sandboxes/{name}` | Deletes the CR; `sandbox-controller` tears down the rest |
| `GET` | `/health` | Liveness |

The Sandboxes tab lists every sandbox with its phase, wired-up services, mock count and age,
auto-refreshing every ~3s while any sandbox is still `Pending`. "New sandbox" builds the CR
from checkboxes over the service list, with a "use migrated DB" toggle for DB-backed services,
optional image overrides, env vars and initial mock rules. "Try it" calls the chain endpoint
with `X-Sandbox-ID: <name>` and shows which version answered per service.

The frontend reaches it through nginx's `/sandboxes-api/` location, proxied the same way as
`/api/` and `/mocks/`.

## Mocking external APIs

`service-d` calls two simulated third-party APIs — `external-payments` and
`external-weather` — from its `/info` endpoint. They live in namespace `external`, **outside**
the mesh (not Istio-injected): real third parties aren't sidecar-proxied either. Application
code never knows a mock exists; Istio decides, exactly like the sandbox routing above.

```mermaid
flowchart LR
    D[service-d] -->|X-Sandbox-ID?| VS{VirtualService}
    VS -->|header present| MP[mock-proxy<br/>WireMock]
    VS -->|no header| EXT[external-payments /<br/>external-weather]
    MP -->|rule enabled for<br/>this sandbox id| MOCK[(mocked response<br/>X-Mock: true)]
    MP -->|no matching rule<br/>catch-all proxies| UP[external-payments-upstream /<br/>external-weather-upstream]
    UP --> EXT

    classDef sb stroke:#f59e0b,stroke-width:2px
    class MP,MOCK sb
```

| `X-Sandbox-ID` | Rule for that sandbox id | Where it lands | `mocked` |
| --- | --- | --- | --- |
| absent | — | straight to `external-payments`/`external-weather` | `false` |
| present | none / disabled | `mock-proxy` → catch-all (priority 10) → `-upstream` → real service | `false` |
| present | enabled | `mock-proxy` → managed stub (priority 1) → mocked response | `true` |
| present, different sandbox id | rule exists for another id | catch-all proxies through (header doesn't match `equalTo`) | `false` |

WireMock evaluates lower priority numbers first, so a sandbox-specific rule always wins over
the passthrough catch-all when both could match.

**Loop avoidance.** Each external has two Services pointing at the same pods:
`external-payments` (the catch-all's origin) and `external-payments-upstream` (what the
catch-all's `proxyBaseUrl` targets). No VirtualService ever matches the `-upstream` host, so
WireMock's outbound proxy call can never route back into itself.

**mock-manager** (`mock-manager/`, hexagonal FastAPI) is the source of truth for rules, stored
in SQLite on a PVC. Every write — and a periodic timer every `RECONCILE_INTERVAL_SECONDS`
(default 15s) — reconciles enabled rules into WireMock stubs, tagged `managed_by: mock-manager`
so reconcile only ever touches stubs it owns, never catch-alls or hand-made GUI stubs.
Reconciliation also runs on startup, so a killed `mock-proxy` pod self-heals within one interval.

```bash
kubectl --context colima-sandbox-poc port-forward svc/mock-proxy 8090:80
# WireMock GUI: http://localhost:8090/__admin/webapp/
# Admin API:    http://localhost:8090/__admin/mappings

kubectl --context colima-sandbox-poc port-forward svc/mock-manager 8091:80
# REST API: http://localhost:8091/rules
```

Create a rule directly against `mock-manager`:

```bash
curl -s -X POST http://localhost:8091/rules -H 'Content-Type: application/json' -d '{
  "sandbox_id": "test-123", "host": "external-payments",
  "method": "POST", "path": "/charge", "status": 402,
  "headers": {}, "body": {"error": "card_declined"}, "delay_ms": 0, "enabled": true
}'

curl -s -H "X-Sandbox-ID: test-123" http://localhost:8081/api/chain \
  | jq '.downstream.downstream.d.external.payments'
# { "http_status": 402, "mocked": true, "data": { "error": "card_declined" } }
```

**Why one shared `mock-proxy`, not one per sandbox.** This POC keeps a single WireMock
deployment and has the controller seed rules into it scoped by `sandbox_id`, instead of one
WireMock per sandbox. Deliberate tradeoffs: no per-team authorization on the shared admin API,
abandoned sandboxes' stubs pile up unless swept by the orphan-GC sweep (see Gotchas), and one
pod is a single point of failure for every sandbox's mocks at once — though a bad reconcile
only breaks its own managed stubs, since the reconciler processes each rule independently.

## Observability

```bash
kubectl --context colima-sandbox-poc port-forward -n observability svc/grafana 3000:3000
```

http://localhost:3000/d/sandbox-routing (no login) — traces, logs and the OTel pipeline:

```mermaid
flowchart LR
    S[services] -->|OTLP| OC[OTel Collector]
    OC --> T[Tempo<br/>traces]
    OC --> L[Loki<br/>logs]
    T -->|service graph<br/>metrics| P[Prometheus]
    T --> G[Grafana]
    L --> G
    P --> G
```

A single trace shows the whole mechanism — same `sandbox.id` attribute on every span, only
`service-c`'s version differs:

```
service-a  v=baseline   ROOT   GET /chain   sandbox.id=test-123
service-b  v=baseline   child  GET /chain   sandbox.id=test-123
service-c  v=test-123   child  GET /info    sandbox.id=test-123
service-d  v=baseline   child  GET /info    sandbox.id=test-123
```

**Kiali** (`k8s/kiali/`, the official Istio 1.31 addons) renders the routing graph itself:

```bash
kubectl --context colima-sandbox-poc -n istio-system port-forward svc/kiali 20001:20001
```

http://localhost:20001/kiali/ → Graph, namespaces `default` + `external`, "Versioned app
graph", Traffic Animation on. Three distinct edges appear depending on the request: direct to
`external-payments` (no header), through `mock-proxy` to the `-upstream` passthrough (header,
no enabled rule), or ending at `mock-proxy` (header, enabled rule — the response never reaches
the real external).

## Testing

Unit tests (each service that has them):

```bash
cd mock-manager && uv run pytest -q
cd sandbox-controller && uv run pytest -q
cd sandbox-api && uv run pytest -q
```

Frontend type-check:

```bash
cd frontend && pnpm tsc --noEmit
```

End-to-end, against a live cluster:

```bash
cd e2e && uv sync
uv run pytest -v                    # full suite
uv run pytest -v -m "not disruptive" # skip pod-kill / scale-down checks
```

Notes:

- Only run one E2E session at a time — tests share cluster state.
- Requires `sandbox-a-1` to already exist; the suite's session fixture snapshots it and
  asserts it's untouched at the end of the run.
- Disruptive tests (`-m disruptive`) restore cluster state on their own before finishing.
- The orphan-GC test needs at least one other live sandbox to exist, because the controller's
  circuit breaker refuses to delete anything when it sees zero `Sandbox` CRs (see Gotchas).

## Gotchas

| Symptom | Cause |
| --- | --- |
| `kubectl port-forward` to an in-mesh service ignores `X-Sandbox-ID` | Tunnels straight to one pod, bypassing the sidecar. If that pod is a sandbox pod, every headerless request gets silently routed into it. Always enter through the ingress gateway; keep direct service port-forwards as debug aids only |
| Header never matches | `VirtualService` must use lowercase `x-sandbox-id` — HTTP/2 normalizes, Istio's match is case-sensitive |
| Routing ignored entirely | Service ports must be named `http`, or Istio treats traffic as plain TCP |
| `426 Upgrade Required` | nginx needs `proxy_http_version 1.1`; the sidecar rejects HTTP/1.0 |
| Frontend always shows baseline | nginx drops unknown headers — needs `proxy_set_header X-Sandbox-ID $http_x_sandbox_id` |
| No database spans in traces | `setup_telemetry()` must run **before** importing the psycopg module; instrumentation is monkey-patching |
| `ImagePullBackOff` | Unquoted `$s:latest` in zsh builds a mangled tag |
| `service-c`/`service-e` 500 with `column "name" does not exist` | Keying query shape off `VERSION == "sandbox"` breaks once `VERSION` is an arbitrary sandbox id. Schema selection reads a dedicated `DB_SCHEMA` env var instead |
| `sandbox-controller` gets `MaxRetryError ... localhost:80` from the k8s API | The `kubernetes` Python client loads no config by default; call `load_incluster_config()` first |
| A deleted `Sandbox`'s mock rules occasionally survive | Delete-time cleanup is best-effort so it never blocks the finalizer. A periodic sweep (`MOCK_GC_INTERVAL_SECONDS`, default 30s) deletes rules with no matching CR — but deletes nothing if the CR list comes back empty, a circuit breaker against mistaking "can't see sandboxes" for "no sandboxes exist" |
| `sandbox-controller` occasionally 409s applying routing objects | Two sandboxes reconciling the same service race the GET+replace; retried on `409` with a fresh GET, bounded at 3 attempts |
| A mock rule with `status: 503` gets silently retried into a `504` | The external routes' retry policy intentionally excludes `503` from `retryOn`, since that route also carries deliberately-mocked responses |

## Known limitations (POC)

Accepted deliberately, given this repo's scope:

- **No control-plane authentication/authorization.** `sandbox-api`, `mock-manager`, and the
  WireMock admin API are all unauthenticated and reachable through the frontend's nginx proxy.
- **`X-Sandbox-ID` is client-supplied and unverified.** Anything sending the header can route
  into any sandbox, including one it doesn't own — the same trust model Uber (SLATE) and
  Signadot document for their own request-scoped sandboxing; see
  [`docs/PRODUCTION-SYSTEMS.md`](docs/PRODUCTION-SYSTEMS.md).
- **`sandbox-controller`'s RBAC is namespace-wide, not label-scoped.** The
  `managed-by: sandbox-controller` label is an application-level convention it honors, not a
  Kubernetes-enforced boundary.
- **One shared, single-replica `mock-proxy` serves every sandbox, never baseline** (see
  tradeoffs above), backed by **SQLite on a single RWO PVC with no replication or failover.**
- **Kiali's signing key is the placeholder `CHANGEME`** — rotate before using a shared cluster.
- **No frontend test suite and no CI.** Frontend correctness relies on manual verification
  (`tsc --noEmit` + `vite build` + click-through); none of the services here run in CI.

## Layout

```
service-a/  service-b/    propagate the header (middleware + httpx hook)
service-c/  service-e/    read the database; two deployments each
service-d/                control — no database, always baseline; calls the externals
external-payments/        fake third-party API, POST /charge — outside the mesh
external-weather/         fake third-party API, GET /weather — outside the mesh
mock-manager/             hexagonal FastAPI; owns mock rules, reconciles WireMock stubs
sandbox-controller/       hexagonal kopf operator; owns Sandbox CRs, generates Deployments,
                           Istio routing and mock-manager rules
sandbox-api/              hexagonal FastAPI; reads/writes Sandbox CRs only, no reconcile
                           logic — the self-service API behind the Sandboxes tab
frontend/                 React + TypeScript + nginx proxy to service-a, mock-manager and
                           sandbox-api
db/migrations/            001 baseline, 002 sandbox-only breaking migration
k8s/istio/                Gateway + VirtualService binding istio-ingressgateway to frontend,
                           and VirtualServices routing externals through mock-proxy (per-
                           sandbox routing objects are generated at runtime, not checked in)
k8s/sandbox-controller/   CRD, RBAC, Deployment for the sandbox-controller operator
k8s/sandbox-api/          RBAC, Deployment, Service for the self-service sandbox API
k8s/sandboxes/            example Sandbox CRs (test-123, team-b, team-c)
k8s/external/             external Deployments + Services, each with an "-upstream" twin
                           to avoid proxy loops
k8s/mocking/              mock-proxy (WireMock), its catch-all mappings, mock-manager
k8s/observability/        Tempo, Loki, Prometheus, OTel Collector, Grafana
k8s/kiali/                Kiali + Prometheus (official Istio addons)
```

## Further reading

[`docs/FORWARD-COMPATIBILITY.md`](docs/FORWARD-COMPATIBILITY.md) — the harder problem this
POC exposes: a sandbox writing a **new enum value** an older service can't read. No schema
migration, no loud failure, and a rollback doesn't undo it.

[`docs/PRODUCTION-SYSTEMS.md`](docs/PRODUCTION-SYSTEMS.md) — how Uber (SLATE), Lyft,
DoorDash and Signadot implement this same pattern, what they use instead of a custom header,
and their own statements on why none of them isolate shared state.

## Cleanup

```bash
colima delete sandbox-poc
```
