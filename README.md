# Request-Scoped Sandboxes with Istio

A working proof of concept for **request-scoped sandbox environments**: a single HTTP header
routes a request to a modified version of one service, while everything else in the stack
stays shared. No routing logic lives in application code — Istio decides.

This is the pattern Uber (SLATE), Lyft (staging overrides), DoorDash (DoorTest) and
Signadot all converged on, reproduced end to end on a local cluster, including the parts
that are usually glossed over: **the database, the redeploy blast radius, and the failure
you get when you ignore it.**

```
frontend (React)
  │  X-Sandbox-ID: test-123
  ▼
service-a ──► service-b ──┬──► service-c  (baseline | sandbox) ──► postgres
                          │
                          ├──► service-e  (baseline | sandbox) ──► postgres
                          │
                          └──► service-d  (baseline only, no database)
```

## What this demonstrates

| Question | Answer this POC gives |
| --- | --- |
| Can infrastructure pick a service version from a header? | Yes — `VirtualService` + `DestinationRule`, zero app logic |
| How does the header survive a call chain? | Middleware + `ContextVar` + httpx event hook |
| What happens to the database? | Clone it, migrate the clone, leave baseline untouched |
| Who has to be redeployed? | **Everything that reads the migrated database**, changed or not |
| What if you get that wrong? | `psycopg.errors.UndefinedColumn: column "name" does not exist` |

The last two rows are the interesting ones. `service-e` has **no code change at all** for
this sandbox — both of its deployments run the identical image. It needs a sandbox
deployment purely because the database it reads was migrated.

> **The sandbox boundary follows the data dependency graph, not the diff.**

## Routing rule

| `X-Sandbox-ID` | Destination subset |
| --- | --- |
| `test-123` | `sandbox` |
| anything else, or absent | `baseline` |

Defined in `k8s/istio/service-c-routing.yaml` and `service-e-routing.yaml`:

```yaml
http:
  - name: sandbox-route
    match:
      - headers:
          x-sandbox-id:
            exact: test-123
    route:
      - destination: { host: service-c, subset: sandbox }
  - name: baseline-route
    route:
      - destination: { host: service-c, subset: baseline }
```

`service-d` has no such rule. It receives the header and still answers `baseline` — the
control that proves only the services you *choose* to sandbox are replaced.

## What the application knows

Each service knows exactly two things:

1. The hostname of its downstream dependency (`http://service-c`).
2. That it must copy `X-Sandbox-ID` onto outgoing requests.

It does **not** know which sandboxes exist, which versions exist, where the sandbox version
runs, or any routing rule.

### How propagation works

`sandbox_propagation.py` (in `service-a` and `service-b`) handles both halves so no request
handler ever touches the header:

```python
class SandboxPropagationMiddleware(BaseHTTPMiddleware):        # INBOUND
    async def dispatch(self, request, call_next):
        token = current_sandbox_id.set(request.headers.get(SANDBOX_HEADER))
        try:
            return await call_next(request)
        finally:
            current_sandbox_id.reset(token)      # without this, ids leak between requests

async def inject_sandbox_header(request: httpx.Request) -> None:   # OUTBOUND
    sandbox_id = current_sandbox_id.get()
    if sandbox_id is not None:
        request.headers[SANDBOX_HEADER] = sandbox_id
```

A middleware alone is not enough — it only sees inbound traffic. The `ContextVar` carries
the value to the outbound client without threading it through function arguments. The
`finally` reset is not optional: in an async server handling concurrent requests, a request
with no header would otherwise inherit a concurrent request's sandbox id.

Handlers just call `client.get(f"{SERVICE_C_URL}/info")` with no headers argument at all.

> Production systems (Uber, Lyft, DoorDash) use **tracing baggage** instead of a custom
> header, precisely to avoid writing this module in every service. See
> [Relation to production systems](#relation-to-production-systems).

## The database workflow

When a sandbox changes the schema, the data has to be sandboxed too:

```bash
./db/clone-and-migrate.sh
```

1. Seed `postgres-baseline` with `db/migrations/001_baseline.sql`.
2. `pg_dump` baseline, restore into `postgres-sandbox` — the clone.
3. Apply `db/migrations/002_split_name_sandbox_only.sql` **to the clone only**.

The migration splits `name` into `brand` + `model` and **drops `name`**:

```
postgres-baseline   products(id, name, price_cents, stock)
postgres-sandbox    products(id, price_cents, stock, brand, model)
```

Baseline is never migrated. Production schema and data stay untouched.

### Why service-e must be redeployed

`service-e` reads `name`. Its code did not change for this sandbox — both deployments use
the same `service-e:latest` image, and only `DATABASE_URL` differs. But pointed at the
migrated clone, it fails:

```
psycopg.errors.UndefinedColumn: column "name" does not exist
```

So the sandbox needs a `service-e-sandbox` deployment even though nobody edited its code.
Any service that reads a migrated database needs a sandbox instance pointing at the clone.

This POC ships `service-e` already adapted to both schemas, so the chain succeeds. To
reproduce the failure, revert `service-e/main.py` to call `fetch_products_legacy()`
unconditionally and send a request with the sandbox header.

### The harder variant: new enum values

Dropping a column fails **loudly and immediately**. A subtler version of the same problem
does not:

> A new service version writes a **new enum value** into a shared table. No migration is
> involved — the schema is identical. The old version reads a value it has never heard of.

This fails *silently*: an unmatched `case`, a `.get()` returning `None`, or a fallback to a
default that happens to be a real, meaningful value. And unlike a column drop, **rolling
back the code does not undo it** — the rows keep the unknown value forever.

Three documented facts make this worse:

- **PostgreSQL enums are append-only.** There is no `ALTER TYPE ... DROP VALUE`
  ([docs](https://www.postgresql.org/docs/current/sql-altertype.html)). Adding a value is
  not rollback-safe either: *"instances of the value could be added to indexes later in the
  same transaction, and then they would still be accessible even if the transaction rolls
  back."*
- **Protobuf's default `0`** means an old reader that discards an unknown value silently
  falls back to whatever value `0` is — which is why the convention is to reserve
  `UNKNOWN = 0` ([protobuf.dev](https://protobuf.dev/programming-guides/enum/)).
- **Contract testing does not catch it.** Pact verifies consumer-supplied *examples*, not
  the whole schema space, so a brand-new enum value no consumer ever exercised passes
  verification cleanly ([pactflow.io](https://pactflow.io/blog/schemas-are-not-contracts/)).

This class of bug exists in any **rolling update**, not just sandboxes — during a rollout
both versions run at once. A sandbox just makes the coexistence permanent instead of
30 seconds long.

Defenses, cheapest first:

| Layer | What it does |
| --- | --- |
| **Tolerant Reader** ([Fowler](https://www.martinfowler.com/bliki/TolerantReader.html)) | Treat "unknown" as a first-class case with a log line, never as the `else` branch |
| **Open enum storage** | `CHECK` constraint or lookup table instead of a native PG enum — both are removable and rollback-safe |
| **Parallel Change** ([Fowler](https://www.martinfowler.com/bliki/ParallelChange.html)) | expand → migrate → contract. Deploy *readers* first, only then write the new value |
| **Write-side guardrail** | Reject writing a value baseline cannot read, turning a silent bug into a loud error |

A sandbox that introduces a new value skips the "deploy readers first" step by
construction — which is exactly why it must write to a **cloned** database, as this POC does.

## Project layout

```
service-a/                  entry service, calls B
service-b/                  calls C, D and E in parallel
service-c/                  two deployments; reads products, version from VERSION env var
service-d/                  control service — no database, always baseline
service-e/                  same image in both deployments, only DATABASE_URL differs
service-*/sandbox_propagation.py   middleware + httpx hook (A and B only)
service-*/telemetry.py      OpenTelemetry setup
service-*/products.py       database access (C and E)
frontend/                   React app, served by nginx, proxies /api to service-a
db/migrations/              001 baseline schema, 002 sandbox-only breaking migration
db/clone-and-migrate.sh     seed, clone, migrate the clone
k8s/deployments/            Deployments (service-c and service-e have baseline + sandbox)
k8s/services/               ClusterIP Services (one per service, shared across versions)
k8s/database/               postgres-baseline and postgres-sandbox
k8s/istio/                  DestinationRule + VirtualService per sandboxed service
k8s/observability/          Tempo, Loki, Prometheus, OTel Collector, Grafana + dashboard
docker-compose.yml          optional, runs the services without Istio
```

## Prerequisites

- A local Kubernetes cluster. These instructions use [Colima](https://github.com/abiosoft/colima)
  (`brew install colima`); minikube, kind or Docker Desktop work too — only step 3 differs.
- `kubectl`
- `istioctl` (`brew install istioctl`)

## Running it

### 1. Start a dedicated local cluster

A separate profile keeps this POC away from any other cluster you have:

```bash
colima start sandbox-poc --kubernetes --cpu 4 --memory 8 --disk 30
```

This registers a `colima-sandbox-poc` kubeconfig context pointing at `127.0.0.1`.

> **Check your context before anything else.** Colima switches your active context on start.
> If you work with remote clusters, pass `--context colima-sandbox-poc` explicitly on every
> command below and confirm the target is local:
> ```bash
> kubectl config view -o jsonpath='{.clusters[?(@.name=="colima-sandbox-poc")].cluster.server}'
> ```
> It must print a `127.0.0.1` address.

### 2. Install Istio and enable sidecar injection

```bash
istioctl install --context colima-sandbox-poc --set profile=demo -y
kubectl --context colima-sandbox-poc label namespace default istio-injection=enabled
```

### 3. Build the images against the cluster's container runtime

Check which runtime the node uses:

```bash
kubectl --context colima-sandbox-poc get nodes \
  -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}'
```

Colima reports `docker://…`, meaning its k3s runs on that profile's Docker daemon. Building
against that daemon is enough — with `imagePullPolicy: IfNotPresent` the pods find the
images locally and never reach a registry:

```bash
export DOCKER_HOST="unix://${HOME}/.colima/sandbox-poc/docker.sock"

for s in a b c d e; do
  docker build -t "service-${s}:latest" "./service-${s}"
done
docker build -t frontend:latest ./frontend
```

> Quote the tag as `"service-${s}:latest"`. Unquoted, zsh reads `$s:latest` as a history
> modifier and silently produces `service-aatest`, which fails with `ImagePullBackOff`.

If the node reports `containerd://…` instead, import each image after building:

```bash
docker save "service-${s}:latest" -o "/tmp/service-${s}.tar"
colima ssh --profile sandbox-poc -- sudo k3s ctr images import - < "/tmp/service-${s}.tar"
```

On minikube use `eval $(minikube docker-env)` before building; on kind use
`kind load docker-image service-a:latest …` after.

### 4. Apply the manifests

```bash
kubectl --context colima-sandbox-poc apply \
  -f k8s/database/ -f k8s/deployments/ -f k8s/services/ -f k8s/istio/
```

### 5. Set up the databases

```bash
KUBECTL="kubectl --context colima-sandbox-poc" ./db/clone-and-migrate.sh
```

It prints both schemas at the end so you can see `name` surviving in baseline and being
replaced by `brand` + `model` in the sandbox clone.

### 6. Wait for the pods

```bash
kubectl --context colima-sandbox-poc get pods -w
```

Every pod should report `2/2` — the application plus its Istio sidecar. If a pod shows
`1/1`, injection did not happen: re-check step 2 and restart the deployments.

### 7. Port-forward

```bash
kubectl --context colima-sandbox-poc port-forward svc/service-a 8080:80
```

## Testing the scenarios

### No header — everything baseline

```bash
curl -s http://localhost:8080/chain | jq '.downstream.downstream | {c: .c.version, d: .d.version, e: .e.version}'
```

```json
{ "c": "baseline", "d": "baseline", "e": "baseline" }
```

### `X-Sandbox-ID: test-123` — C and E move, D does not

```bash
curl -s -H "X-Sandbox-ID: test-123" http://localhost:8080/chain \
  | jq '.downstream.downstream | {c: .c.version, d: .d.version, e: .e.version}'
```

```json
{ "c": "sandbox", "d": "baseline", "e": "sandbox" }
```

`service-c` reports `"schema": "brand+model"` here and `"schema": "name"` without the
header — the same code path choosing a query based on which database it was pointed at.

### An unknown sandbox id — still baseline

```bash
curl -s -H "X-Sandbox-ID: some-other-id" http://localhost:8080/chain | jq
```

The header propagates end to end (you can see it in every service's logs) but no route
matches it, so the default route wins. **This is the scenario that proves the application
is not deciding anything** — it behaves identically in all three cases.

### Watching which pod answered

```bash
kubectl --context colima-sandbox-poc logs -l app=service-c,version=baseline -c service-c -f
kubectl --context colima-sandbox-poc logs -l app=service-c,version=sandbox  -c service-c -f
```

Each service logs one line per request:

```
service=C version=sandbox schema=brand+model products=5 sandbox_id=test-123
```

Run both in separate terminals and fire the two curls: only one pod logs each request.

## Frontend

```bash
kubectl --context colima-sandbox-poc port-forward svc/frontend 5173:80
```

Open http://localhost:5173. Three buttons send the three scenarios and the page shows which
version answered each call, with the raw JSON per service.

Two nginx settings in `frontend/nginx.conf` matter:

```nginx
proxy_http_version 1.1;                                 # without it: 426 Upgrade Required
proxy_set_header X-Sandbox-ID $http_x_sandbox_id;       # nginx drops unknown headers
```

The Istio sidecar rejects HTTP/1.0 from upstream, and nginx does not forward custom headers
by default — without the second line the sandbox id dies at the proxy and the demo silently
always shows baseline.

## Observability

```bash
kubectl --context colima-sandbox-poc port-forward -n observability svc/grafana 3000:3000
```

Open http://localhost:3000/d/sandbox-routing — anonymous access is enabled.

```
services ──OTLP──► OTel Collector ──┬──► Tempo (traces) ──► Prometheus (service graph)
                                     └──► Loki (logs)
                                              └──► Grafana
```

Dashboard panels:

| Panel | Shows |
| --- | --- |
| Service graph | Nodes and edges, including `service-c → catalog` split per version |
| Calls per edge | Request rate per client → server pair |
| Database calls per version | Which Postgres each version talks to |
| service-c baseline / sandbox logs | Side-by-side, one pod logs each request |
| Header propagation table | Time, Service, Version, Sandbox ID, Trace ID per hop |
| Traces | Full A → B → C/D/E span tree |

A single trace shows the whole mechanism in four lines:

```
service-a  v=baseline  ROOT   GET /chain   sandbox.id=test-123
service-b  v=baseline  child  GET /chain   sandbox.id=test-123
service-c  v=sandbox   child  GET /info    sandbox.id=test-123
service-d  v=baseline  child  GET /info    sandbox.id=test-123
```

Same header everywhere, different versions answering. Service D receives the sandbox id and
still answers baseline, because no routing rule was written for it.

### Instrumentation gotcha

`setup_telemetry()` must run **before** importing the module that uses psycopg:

```python
setup_telemetry(f"service-{SERVICE_NAME.lower()}", VERSION)

from products import fetch_products_legacy, fetch_products_split   # noqa: E402 — deliberate
```

`PsycopgInstrumentor` monkey-patches `psycopg.connect`. If `products` is imported first it
captures the unpatched reference and **no database spans are produced at all** — the service
graph shows no database node and nothing errors. The mid-file import is deliberate.

## Running without Istio (optional)

```bash
docker compose up --build
curl -s -H "X-Sandbox-ID: test-123" http://localhost:8000/chain | jq
```

The header still propagates through the whole chain, but C always answers `baseline` —
there is no sandbox deployment and no Istio to route to it. That is the point:
**propagation is the application's job, routing is the infrastructure's job.**

## Relation to production systems

The mechanism here matches what large teams published, with one deliberate difference.

| | Context carrier | Routing layer |
| --- | --- | --- |
| **Uber SLATE** | Jaeger baggage `request-tenancy` = `uber/test/slate/{ID}` | Edge-Gateway + host-routing-agent |
| **Lyft** | OpenTracing baggage in `x-ot-span-context` | Custom Envoy HTTP filter |
| **DoorDash** | HTTP header → OTel baggage at the CDN, tenant `L0:L1` | OpenTelemetry + service mesh |
| **Signadot** | `sd-routing-key` in OTel baggage | Istio, or their own DevMesh sidecar |
| **This POC** | Custom `X-Sandbox-ID` header | Istio `VirtualService` |

The custom header is a teaching choice — it makes propagation explicit and visible in
`sandbox_propagation.py`. In production, tracing baggage is preferable because it already
propagates. The [CNCF puts it plainly](https://www.cncf.io/blog/2024/05/28/is-testing-in-production-even-possible/):
*"You can use a custom header… you have to modify the code of each service to pass the header."*

**On shared state, none of them solved it.** They accepted it:

- Uber: *"SUT uses production instances of dependencies by default, for guaranteeing the
  best fidelity while ensuring production safety"*, and
  *"most share production datastores"* — isolation is opt-in per service.
- Lyft: *"It talks to standard databases"* — no per-sandbox database isolation published.
- Signadot: *"Most teams start with the shared database model for convenience and use
  ephemeral databases only when necessary."*
- DoorDash: `tenant_id` columns via DBMesh, plus application guardrails so
  *"test consumers cannot place orders with real stores."*

All of them abandoned full environment replication first — DoorDash because
*"running all the microservices requires a lot of hardware resources"*, Lyft because their
"Onebox" system *"reached a point where it could not scale anymore"*.

This POC takes the stricter path (clone the database per sandbox) because it is tractable at
small fan-out. If 4–5 services share one database, cloning is very manageable. At Uber's
scale a request crosses dozens of datastores and the clone boundary explodes — which is why
they tag instead. For larger databases, copy-on-write branching
([Neon](https://neon.com/docs/introduction/branching): *"giving ten engineers their own copy
of a 50 GB database doesn't cost you 500 GB"*) makes the clone approach viable again.

**Cache isolation is undocumented industry-wide.** No company or vendor source found —
including Signadot's own docs — publishes a concrete strategy for it.

## Design notes

- The header match in the `VirtualService` uses the lowercase key `x-sandbox-id`. HTTP/2
  normalizes header names to lowercase and Istio's match is case-sensitive, so the uppercase
  spelling would never match.
- Service ports are named `http` so Istio detects the protocol. Without the name, traffic is
  treated as plain TCP and header-based routing is ignored entirely.
- The `service-c` and `service-e` Services select on `app` only, deliberately omitting
  `version`, so one Service covers both deployments. Splitting into subsets is the
  `DestinationRule`'s job.
- The two Postgres Services **do** select on `version` — they are different databases, not
  two replicas, and must never be load-balanced between.
- Deployments are named `service-x-baseline` / `service-x-sandbox` uniformly. Kubernetes
  requires unique names, and `version` is a label on every pod regardless of the object name.

## Cleanup

```bash
kubectl --context colima-sandbox-poc delete -f k8s/istio/ -f k8s/services/ \
  -f k8s/deployments/ -f k8s/database/
kubectl --context colima-sandbox-poc delete namespace observability
```

Or remove the whole cluster:

```bash
colima delete sandbox-poc
```
