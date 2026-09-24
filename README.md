# Request-Scoped Sandboxes with Istio

One HTTP header routes a request to a modified version of a service. Everything else stays
shared. **No routing logic in application code** — Istio decides.

Sandboxes are not hand-written Kubernetes manifests. A team applies a `Sandbox` custom
resource naming the id and the services it touches; the `sandbox-controller` operator
generates the Deployments, the Istio routing, and the mock rules from it. See
[Dynamic sandboxes](#dynamic-sandboxes) for how and why.

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

Solid lines are the default path. Dashed lines activate only when the header matches.

| `X-Sandbox-ID` | service-c | service-e | service-d |
| --- | --- | --- | --- |
| absent | baseline | baseline | baseline |
| `test-123` | **sandbox** | **sandbox** | baseline |
| anything else | baseline | baseline | baseline |

`service-d` receives the header and still answers baseline — the control that proves only
the services you *choose* to sandbox get replaced.

## The point

`service-e` has **no code change** for this sandbox. Both deployments run the identical
image; only `DATABASE_URL` differs. It needs a sandbox deployment purely because the
database it reads was migrated.

> **The sandbox boundary follows the data dependency graph, not the diff.**

Point the unmodified `service-e` at the migrated clone and it dies:

```
psycopg.errors.UndefinedColumn: column "name" does not exist
```

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

Two halves, both in `sandbox_propagation.py`:

```python
class SandboxPropagationMiddleware(BaseHTTPMiddleware):        # INBOUND
    async def dispatch(self, request, call_next):
        token = current_sandbox_id.set(request.headers.get(SANDBOX_HEADER))
        try:
            return await call_next(request)
        finally:
            current_sandbox_id.reset(token)      # or ids leak between concurrent requests

async def inject_sandbox_header(request: httpx.Request) -> None:   # OUTBOUND
    if (sandbox_id := current_sandbox_id.get()) is not None:
        request.headers[SANDBOX_HEADER] = sandbox_id
```

A middleware alone only sees inbound traffic. The `ContextVar` carries the value to the
outbound client, so handlers just call `client.get(url)` with no headers argument.

## The database

```bash
./db/clone-and-migrate.sh
```

Seeds baseline, `pg_dump`s it into the sandbox instance, then migrates **the clone only**:

```
postgres-baseline   products(id, name, price_cents, stock)
postgres-sandbox    products(id, price_cents, stock, brand, model)   ← name dropped
```

Baseline is never migrated. Every service that reads the migrated clone needs a sandbox
deployment — changed or not.

`service-c` and `service-e` pick their query shape from `DB_SCHEMA` (`legacy` | `split`), not
from the sandbox id. A `Sandbox` CR sets `DB_SCHEMA=split` alongside `DATABASE_URL` when it
points a service at `postgres-sandbox`. Keying application logic off the routing `VERSION`
label (which is now an arbitrary sandbox id, not the fixed literal `sandbox`) would silently
break the moment two differently-named sandboxes exist.

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

# 6. wait for 2/2 (app + sidecar; external-* and Kiali/Prometheus pods stay 1/1
# — they are not mesh-injected), then forward the Istio ingress gateway —
# the single entry point, not a direct service port-forward (see below)
kubectl --context colima-sandbox-poc get pods -w
kubectl --context colima-sandbox-poc -n istio-system port-forward svc/istio-ingressgateway 8081:80

# 7. create a sandbox
kubectl --context colima-sandbox-poc apply -f k8s/sandboxes/test-123.yaml
kubectl --context colima-sandbox-poc get sandboxes -w
```

> Quote the tag as `"service-${s}:latest"`. Unquoted, zsh reads `$s:latest` as a history
> modifier and silently builds `service-aatest` → `ImagePullBackOff`.

Other clusters: minikube needs `eval $(minikube docker-env)` before building; kind needs
`kind load docker-image …` after. If `get nodes` reports `containerd://` rather than
`docker://`, import the images with `k3s ctr images import`.

## Try it

`test-123` must exist as a `Sandbox` CR first (step 7 above, or see
[Dynamic sandboxes](#dynamic-sandboxes)). All traffic goes through the Istio ingress gateway
(step 6) — `http://localhost:8081/api/` is nginx's proxy to `service-a`, the entry point into
the mesh:

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

The third case is the one that matters: the header propagates end to end (check the logs)
but no route matches, so baseline wins. **The application behaves identically in all three.**

> Why the gateway and not `kubectl port-forward svc/service-a`: a service port-forward tunnels
> straight to one pod's port, bypassing the Istio sidecar entirely — the client never goes
> through the mesh, so `X-Sandbox-ID` is silently ignored (see the gotcha table). Worse, if
> that port-forward happens to land on a sandboxed pod, *every* headerless request gets routed
> into that sandbox instead of baseline. The ingress `Gateway`/`VirtualService` in
> `k8s/istio/gateway.yaml` routes `*` to `frontend`; nginx's own sidecar then calls `service-a`
> as a normal in-mesh client, so header-based routing applies exactly like it does for any other
> in-mesh caller. Routing straight from the gateway to `service-a` was considered and rejected:
> the controller-generated `VirtualService` for `service-a` has no `gateways:` field (mesh-only,
> confirmed via `kubectl get vs service-a -o yaml`), so a gateway route that skipped nginx would
> never see the per-sandbox routes at all — only `frontend` is bound to the gateway.

Watch which pod answered:

```bash
kubectl --context colima-sandbox-poc logs -l app=service-c,version=test-123 -c service-c -f
```

## Frontend

http://localhost:8081/ through the gateway port-forward from [Quick start](#quick-start) step
6 — the canonical entry point, mesh routing and all. A direct
`kubectl --context colima-sandbox-poc port-forward svc/frontend 5173:80` also renders the UI,
but it's a debug aid only: nginx's own outbound calls still go through its sidecar either way,
so sandbox routing keeps working from `5173` too — it's `svc/service-a` (and any other
mesh-internal service) you must never port-forward directly for routing purposes, since that's
the hop that bypasses the sidecar.

http://localhost:8081/ — the default **Sandboxes** tab is the self-service UI (see
[Self-service UI](#self-service-ui)). A **Chain** tab keeps the three original buttons, one
per scenario, showing which version answered. A **Mocks** tab manages sandbox mock rules
against `mock-manager`.

## Mocking external APIs

`service-d` calls two simulated third-party APIs — `external-payments` and
`external-weather` — from its `/info` endpoint. They live in namespace `external`, **outside**
the mesh (not Istio-injected): real third parties are not sidecar-proxied either. Application
code never knows a mock exists; Istio decides, exactly like the `service-c`/`service-e`
sandbox routing above.

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

Managed stubs are priority 1, catch-alls are priority 10 — WireMock evaluates lower numbers
first, so a sandbox-specific rule always wins over the passthrough when both could match.

**Loop avoidance.** Each external has two Kubernetes Services pointing at the same pods:
`external-payments` (what the VirtualService's baseline route and the catch-all's origin
represent) and `external-payments-upstream` (what the catch-all's `proxyBaseUrl` targets). No
VirtualService ever matches the `-upstream` host, so WireMock's outbound proxy call can never
be re-routed back into itself.

**mock-manager** (`mock-manager/`, hexagonal: `domain` → `application` → `infrastructure`/`api`)
is the source of truth for rules, stored in SQLite on a PVC. Every write — and a periodic timer
every `RECONCILE_INTERVAL_SECONDS` (default 15s) — reconciles enabled rules into WireMock stubs
via its admin API, tagged `metadata.managed_by: mock-manager`. Reconcile only ever deletes stubs
carrying that tag, so it never touches the catch-alls or anything created by hand in the GUI.
Because reconciliation runs on startup too, killing the `mock-proxy` pod and losing all
in-memory stubs self-heals within one interval.

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

### Gotchas specific to mocking

| Symptom | Cause |
| --- | --- |
| WireMock `PUT /__admin/mappings/{id}` returns `400 … is not a valid UUID` | Stub ids must be canonical UUIDs (`str(uuid.uuid4())`), not bare hex (`uuid4().hex`) |
| Catch-all mappings duplicate 3× after a ConfigMap-mounted ConfigMap change | Mounting a ConfigMap at the whole `mappings/` directory exposes Kubernetes' `..data` symlink-swap layout; WireMock's mapping loader walks it and discovers each file through multiple paths. Mount each JSON key individually with `subPath` instead |
| `mock-manager` reconcile fails forever after one bad rule | A single failing WireMock upsert must not abort the whole reconcile loop for every other rule — the reconciler processes each stub independently |
| Host header for the catch-all's `host: { contains: … }` matcher | Istio preserves the original `Host`/`:authority` when a `VirtualService` reroutes to a different destination Service — no `headers.request.set` rewrite was needed; verified via `/__admin/requests` in the WireMock journal |
| `additionalProxyRequestHeaders` doesn't add response headers | For adding a header to a *proxied* response (not the proxied request), plain `response.headers` alongside `proxyBaseUrl` works on this WireMock build — confirmed via the `X-Mock-Proxy: forwarded` header on catch-all responses |

## Dynamic sandboxes

Early on, sandboxes were hand-written: a `service-X-sandbox` Deployment plus a
hand-edited `DestinationRule`/`VirtualService` per service, both committed to this repo.
That breaks the moment two teams want their own sandbox on the same service — **Istio
does not merge multiple mesh `VirtualService` objects for the same host.** Whichever one
the control plane picks wins outright; the other's routes are silently ignored. A shared,
hand-edited file is the only way to add a route, which means every sandbox is a merge
conflict waiting to happen.

The fix is a `Sandbox` custom resource plus a controller that owns the generated objects:

```bash
kubectl --context colima-sandbox-poc apply -f k8s/sandboxes/test-123.yaml
kubectl --context colima-sandbox-poc get sandboxes
# NAME       PHASE   MESSAGE                            AGE
# test-123   Ready   all sandboxed services available   12s

kubectl --context colima-sandbox-poc delete -f k8s/sandboxes/test-123.yaml
```

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

`sandbox-controller/` (`domain` → `application` → `infrastructure`, same hexagonal shape
as `mock-manager/`) reconciles on every `Sandbox` create/update/delete **and** on a
`ROUTING_INTERVAL_SECONDS` timer, so a deployment that becomes ready between events still
gets routed. A sandbox is only added to a service's `VirtualService`/`DestinationRule`
once its Deployment reports `availableReplicas >= 1` — routing a not-yet-ready pod is how
you get `503 no healthy upstream`. Deployments carry an `ownerReference` to their `Sandbox`,
so deleting the CR garbage-collects them; the controller only has to clean up routing and
mock rules explicitly. `DestinationRule`/`VirtualService` objects are labeled
`app.kubernetes.io/managed-by: sandbox-controller` — the controller only ever touches
objects carrying that label, so it can share `k8s/istio/` with hand-written entries like
`external-payments`/`external-weather` without stepping on them.

**Two sandboxes on one service, proven, not asserted:**

```bash
kubectl --context colima-sandbox-poc apply -f k8s/sandboxes/team-c.yaml   # also targets service-c
kubectl --context colima-sandbox-poc get vs service-c -o jsonpath='{.spec.http[*].name}'
# sandbox-team-c sandbox-test-123 baseline-route
curl -s -H "X-Sandbox-ID: team-c"  localhost:8081/api/chain | jq -c '.downstream.downstream.c.version'   # "team-c"
curl -s -H "X-Sandbox-ID: test-123" localhost:8081/api/chain | jq -c '.downstream.downstream.c.version'  # "test-123"
```

**Why one shared mock-proxy, not one per sandbox.** Each sandbox could get its own WireMock
deployment, fully isolated. Instead this POC keeps the single `mock-proxy` from the static
design and has the controller seed rules into it scoped by `sandbox_id`. Tradeoffs, accepted
deliberately for a POC:

- **Authorization** — every sandbox's rules are reachable through one admin API; there is no
  per-team boundary stopping team A from reading or editing team B's stubs. A production
  version would need per-sandbox auth or a gateway in front of `mock-manager`.
- **Stub count** — WireMock keeps every managed stub in memory; a long-lived cluster with many
  abandoned sandboxes accumulates stubs. Deleting a `Sandbox` CR deletes its rules (`mock-manager`
  deletes them via `DELETE /rules/{id}` for every rule matching that `sandbox_id`), and a
  short-circuited teardown that leaks them is caught by the controller's periodic orphan sweep
  (see the "deleted `Sandbox`'s mock rules occasionally survive" gotcha below).
- **WireMock scenario state is global** — if a rule ever used WireMock Scenarios (stateful
  request sequencing), two sandboxes hitting the same stub would share that state. This repo's
  rules are all stateless (`status`/`body` per request), which sidesteps the problem rather than
  solving it.
- **Blast radius** — one `mock-proxy` pod is a single point of failure for every sandbox's
  mocks at once, and a bad reconcile (e.g. a malformed stub body) can only ever break its own
  managed stubs — the reconciler processes each rule independently — but it is still one
  process serving every team.

A dedicated `mock-proxy` per sandbox would remove all four tradeoffs at the cost of a pod (and
a WireMock admin surface) per sandbox — the same isolation-vs-cost tradeoff the Deployments
already make, just not taken here for the mocking layer.

**Seed, don't override `enabled`.** The controller's job is to make sure a sandbox's declared
mocks *exist*; it is not the source of truth for whether they're *on*. On every reconcile it
matches existing rules by `(sandbox_id, host, method, path)` and only `POST`s the ones that
are missing — it never touches `enabled` on a rule that's already there. Without that rule,
every reapply of a `Sandbox` CR (including the periodic re-reconcile) would silently flip a
mock a team just disabled from the frontend's "Mocks" tab back on.

### Self-service UI

Teams create, inspect and delete sandboxes without ever running `kubectl` or hand-editing a
`Sandbox` CR. `sandbox-api/` (hexagonal FastAPI, same shape as `mock-manager/`) only reads
and writes `Sandbox` custom resources through the Python `kubernetes` client — it has no
reconcile logic of its own, so the CR stays the single source of truth and `sandbox-controller`
still owns every Deployment/routing/mock side effect.

```bash
kubectl --context colima-sandbox-poc port-forward svc/sandbox-api 8092:80
```

http://localhost:5173 → the **Sandboxes** tab (now the default) lists every sandbox with its
phase, wired-up services, mock count and age, auto-refreshing every ~3s while any sandbox is
still `Pending`. "New sandbox" builds the CR from checkboxes over `GET /services` (with a
"use migrated DB" toggle only offered for services that read `DATABASE_URL`), optional image
overrides, extra env vars and initial mock rules. "Try it" calls the chain endpoint with
`X-Sandbox-ID: <name>` and shows which version answered per service plus mocked/real badges
for `service-d`'s externals. "Mocks" jumps to the Mocks tab pre-filtered to that sandbox.

| Method | Path | What it does |
| --- | --- | --- |
| `GET` | `/services` | Baseline (`version=baseline`) services, excluding infra, flagged `uses_db` |
| `GET` | `/sandboxes` | Name, phase, message, service names, mock count, created time |
| `GET` | `/sandboxes/{name}` | Full CR `spec` + `status` |
| `POST` | `/sandboxes` | Creates the CR; `use_migrated_db: true` expands into the `DATABASE_URL`/`DB_PEER_SERVICE`/`DB_SCHEMA=split` triple used by `test-123`; `422` on an invalid DNS-1123 name, `409` if it already exists |
| `DELETE` | `/sandboxes/{name}` | Deletes the CR; `sandbox-controller` tears down the rest |
| `GET` | `/health` | Liveness |

```mermaid
flowchart LR
    UI[Sandboxes tab] -->|REST| API[sandbox-api]
    API -->|get/list/create/delete| CR[Sandbox CR]
    CR -->|create/update/delete<br/>+ periodic timer| CTL[sandbox-controller]
    CTL --> DEP[Deployments] & RT[Istio routing] & MM[mock-manager rules]
```

The frontend reaches it through nginx's `/sandboxes-api/` location, proxied the same way as
`/api/` and `/mocks/`.

## Observability

```bash
kubectl --context colima-sandbox-poc port-forward -n observability svc/grafana 3000:3000
```

http://localhost:3000/d/sandbox-routing (no login).

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

A single trace shows the whole mechanism:

```
service-a  v=baseline   ROOT   GET /chain   sandbox.id=test-123
service-b  v=baseline   child  GET /chain   sandbox.id=test-123
service-c  v=test-123   child  GET /info    sandbox.id=test-123
service-d  v=baseline   child  GET /info    sandbox.id=test-123
```

Same header everywhere, different versions answering.

### Kiali — the routing graph itself

`k8s/kiali/` deploys the official Istio 1.31 addons (Kiali + its own Prometheus instance,
traces wired to Tempo) into `istio-system`:

```bash
kubectl --context colima-sandbox-poc -n istio-system port-forward svc/kiali 20001:20001
```

http://localhost:20001/kiali/ → **Graph**, namespaces `default` + `external`, "Versioned app
graph", Traffic Animation on. Three distinct edges are visible depending on the request:

- No `X-Sandbox-ID` — `service-d` → `external-payments` directly, `mock-proxy` never appears.
- Header present, no enabled rule — `service-d` → `mock-proxy` → `external-payments-upstream`
  (the catch-all passthrough hop is visible as a real edge).
- Header present, enabled rule — `service-d` → `mock-proxy`, and the graph **ends there**: the
  response comes from WireMock itself, so no edge continues on to `external-payments`.

## Layout

```
service-a/  service-b/    propagate the header (middleware + httpx hook)
service-c/  service-e/    read the database; two deployments each
service-d/                control — no database, always baseline; also calls the
                           externals below and propagates the header outbound
external-payments/        fake third-party API, POST /charge — outside the mesh
external-weather/         fake third-party API, GET /weather — outside the mesh
mock-manager/             hexagonal FastAPI service; owns mock rules, reconciles them
                           into WireMock as stubs (SQLite on a PVC)
sandbox-controller/       hexagonal kopf operator; owns Sandbox CRs, generates their
                           Deployments, Istio routing and mock-manager rules
sandbox-api/              hexagonal FastAPI service; reads/writes Sandbox CRs only, no
                           reconcile logic — the self-service API behind the Sandboxes tab
frontend/                 React + TypeScript + nginx proxy to service-a, mock-manager and sandbox-api
db/migrations/            001 baseline, 002 sandbox-only breaking migration
k8s/istio/                Gateway + VirtualService binding istio-ingressgateway to frontend
                           (the single entry point), and VirtualServices routing the externals
                           through mock-proxy (per-sandboxed-service DestinationRule/
                           VirtualService objects are generated at runtime by
                           sandbox-controller, not checked in)
k8s/sandbox-controller/   CRD, RBAC, Deployment for the sandbox-controller operator
k8s/sandbox-api/          RBAC, Deployment, Service for the self-service sandbox API
k8s/sandboxes/            example Sandbox CRs (test-123, team-b, team-c)
k8s/external/             external-payments / external-weather Deployments + Services
                           (each with a second "-upstream" Service to avoid proxy loops)
k8s/mocking/              mock-proxy (WireMock), its catch-all mappings ConfigMap,
                           mock-manager
k8s/observability/        Tempo, Loki, Prometheus, OTel Collector, Grafana
k8s/kiali/                Kiali + Prometheus (official Istio addons)
```

## Gotchas worth knowing

| Symptom | Cause |
| --- | --- |
| `kubectl port-forward` to an in-mesh service ignores `X-Sandbox-ID`, always answers baseline | It tunnels straight to one pod, bypassing the Istio sidecar for that hop entirely — the header never reaches Istio's routing. Worse, if the forwarded pod happens to be a sandbox pod, every headerless request gets silently routed into that sandbox. Always enter through the Istio ingress gateway (`kubectl -n istio-system port-forward svc/istio-ingressgateway 8081:80`); keep direct service port-forwards (`mock-proxy` GUI, Kiali, Grafana, …) as debug aids only |
| Header never matches | `VirtualService` must use lowercase `x-sandbox-id` — HTTP/2 normalizes, Istio's match is case-sensitive |
| Routing ignored entirely | Service ports must be named `http`, or Istio treats traffic as plain TCP |
| `426 Upgrade Required` | nginx needs `proxy_http_version 1.1`; the sidecar rejects HTTP/1.0 |
| Frontend always shows baseline | nginx drops unknown headers — needs `proxy_set_header X-Sandbox-ID $http_x_sandbox_id` |
| No database spans in traces | `setup_telemetry()` must run **before** importing the psycopg module; instrumentation is monkey-patching |
| `ImagePullBackOff` | Unquoted `$s:latest` in zsh builds a mangled tag |
| `service-c`/`service-e` 500 with `column "name" does not exist` against `postgres-sandbox` | The app picked its query shape from `VERSION == "sandbox"`, a literal that only matched the old static deployment. A CR-driven `VERSION` is the sandbox id (`test-123`, `team-c`, …), never the word `sandbox` — schema selection now reads a dedicated `DB_SCHEMA` env var instead |
| kopf's own `status.kopf` progress patch fails with "Patching failed with inconsistencies" | A structural CRD schema **prunes** unknown `status` fields, including kopf's internal bookkeeping; add `x-kubernetes-preserve-unknown-fields: true` on `status` in the CRD so it survives |
| `sandbox-controller` calls the k8s API and gets `MaxRetryError ... localhost:80` | The `kubernetes` Python client defaults to no config loaded at all; the gateway must call `kubernetes.config.load_incluster_config()` before constructing any `*Api()` client |
| `ImportError: cannot import name 'eq' from partially initialized module 'operator'` | Never name the operator's entrypoint module `operator.py` — it shadows the stdlib `operator` module that `kopf`'s own dependency chain imports. Use `main.py` |
| A deleted `Sandbox`'s mock rules occasionally survive in `mock-manager` | Mock cleanup on delete is best-effort: `mock-manager` being unreachable must never block the finalizer, or the `Sandbox` gets stuck `Terminating` forever. `handle_delete` catches and logs any mock-cleanup failure, then still reconciles routing so kopf can release the finalizer. Orphaned rules no longer survive forever, though: a dedicated periodic loop (`MOCK_GC_INTERVAL_SECONDS`, deployed at `30`s, independent of the routing-reconcile loop) lists every rule in `mock-manager`, then lists the live `Sandbox` CRs (in that order, so a sandbox created in between is never mistaken for an orphan), and deletes any rule whose `sandbox_id` has no matching CR — a per-rule failure is logged and skipped so one bad delete never stops the sweep or crashes the loop. Mock rules are considered owned by a `Sandbox` CR, not by the controller's own bookkeeping: a rule manually created for a `sandbox_id` that never was (or no longer is) a real CR gets swept too — that's intentional, not a bug. Circuit breaker: if the CR listing comes back empty (CRD not synced yet, wrong namespace, RBAC returning an empty list) the sweep deletes nothing, because "no sandboxes exist" and "I can't see the sandboxes" look identical from here; the tradeoff is that orphans left after the very last sandbox is deleted wait until the next sandbox exists |
| `sandbox-controller` occasionally 409s applying a `DestinationRule`/`VirtualService` | Two sandboxes reconciling the same service's routing concurrently race the GET+replace in `_apply_custom`. It retries on `409 Conflict` with a fresh GET, bounded at 3 attempts |
| `mock-manager` `POST /rules` returns `409` for a rule that looks new | Rules are unique on `(sandbox_id, host, method, path)`. A second rule with the same tuple conflicts by design — update the existing rule (`PUT`) or use a different `path`/`method` instead |
| A mock rule deliberately configured with `status: 503` gets silently retried into a `504` | `sandbox-route`'s Istio retry policy (`k8s/istio/external-*-routing.yaml`) intentionally excludes `503` from `retryOn` — that route also carries the header-present-but-no-matching-rule catch-all AND the deliberately-mocked-response case, and WireMock returning a configured `503` is not a transport failure. Only `connect-failure,refused-stream,unavailable` are retried; a real mocked `503` (or one with `delay_ms`) reaches the caller unretried and undelayed by `perTryTimeout` |

## Known limitations (POC)

This is a proof of concept for the request-scoped sandbox pattern, not a production system. Known gaps, accepted deliberately for this repo's scope:

- **No control-plane authentication/authorization.** `sandbox-api`, `mock-manager`, and the WireMock admin API are all unauthenticated, and all three are reachable through the frontend's nginx proxy. A production version needs authn/authz on every one of these plus `NetworkPolicy` restricting which pods can reach them directly.
- **`X-Sandbox-ID` is client-supplied and unverified.** Anything sending the header can route itself into any sandbox, including one it doesn't own — there is no check that the caller is entitled to that sandbox id. This is the same trust model Uber (SLATE) and Signadot document for their own request-scoped sandboxing — see [`docs/PRODUCTION-SYSTEMS.md`](docs/PRODUCTION-SYSTEMS.md).
- **`sandbox-controller`'s RBAC is namespace-wide, not label-scoped.** It can read/write every Deployment, DestinationRule, and VirtualService in its namespace, not just the ones it manages — the `managed-by: sandbox-controller` label is an application-level convention it honors, not an RBAC boundary enforced by Kubernetes.
- **One shared, single-replica `mock-proxy` serves every sandbox, never baseline.** Its blast radius is every sandbox's mocks at once (see the "Why one shared mock-proxy, not one per sandbox" tradeoffs above); a crash or bad reconcile degrades every team's sandbox simultaneously, not just one.
- **SQLite on a single RWO PVC is `mock-manager`'s only datastore.** No replication, no failover — losing that PVC loses every mock rule (WireMock stubs self-heal from it on the next reconcile, but the rules themselves are gone for good).
- **Kiali's signing key is the placeholder `CHANGEME`.** Fine for a local POC; must be rotated to a real secret before this manifest is ever pointed at a shared or long-lived cluster.
- **No frontend test suite and no CI.** The frontend's correctness currently relies on manual verification (`tsc --noEmit` + `vite build` + click-through) — there is no automated regression coverage, and none of the services in this repo run in CI.

## E2E tests

```bash
cd e2e && uv sync
uv run pytest -v                    # full suite
uv run pytest -v -m "not disruptive" # skip pod-kill / scale-down checks
uv run pytest -v -k test_two_sandboxes_on_same_service_do_not_cross_talk
```

Requires `sandbox-a-1` to already exist — the suite's session fixture snapshots it and asserts
it is untouched at the end of the run. Disruptive tests (`-m disruptive`) restore cluster state
(scale `mock-manager` back up, wait for a fresh `mock-proxy` pod) on their own before finishing.

## Further reading

[`docs/FORWARD-COMPATIBILITY.md`](docs/FORWARD-COMPATIBILITY.md) — the harder problem this
POC exposes: a sandbox writing a **new enum value** an older service cannot read. No schema
migration, no loud failure, and a rollback does not undo it.

[`docs/PRODUCTION-SYSTEMS.md`](docs/PRODUCTION-SYSTEMS.md) — how Uber (SLATE), Lyft,
DoorDash and Signadot implement this same pattern, what they use instead of a custom header,
and their own statements on why none of them isolate shared state.

## Cleanup

```bash
colima delete sandbox-poc
```
