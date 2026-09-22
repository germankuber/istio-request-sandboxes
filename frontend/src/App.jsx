import { useState } from "react";

const SCENARIOS = [
  { id: "none", label: "No header", sandboxId: null },
  { id: "test-123", label: "X-Sandbox-ID: test-123", sandboxId: "test-123" },
  { id: "unknown", label: "X-Sandbox-ID: unknown-id", sandboxId: "unknown-id" },
];

function versionOf(node) {
  if (!node || node.error) return null;
  return node.version;
}

function Badge({ version }) {
  if (!version) return <span className="badge badge-error">error</span>;
  return <span className={`badge badge-${version}`}>{version}</span>;
}

function ServiceCard({ name, node }) {
  const version = versionOf(node);
  return (
    <div className="card">
      <div className="card-head">
        <strong>service-{name}</strong>
        <Badge version={version} />
      </div>
      {node?.error ? (
        <pre className="error">
          {node.error}
          {"\n"}
          {node.detail}
        </pre>
      ) : (
        <pre>{JSON.stringify(node, null, 2)}</pre>
      )}
    </div>
  );
}

export default function App() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [scenario, setScenario] = useState(SCENARIOS[0]);

  async function send(next) {
    setScenario(next);
    setLoading(true);
    setResult(null);
    try {
      const headers = next.sandboxId ? { "X-Sandbox-ID": next.sandboxId } : {};
      const response = await fetch("/api/chain", { headers });
      setResult(await response.json());
    } catch (error) {
      setResult({ error: String(error) });
    } finally {
      setLoading(false);
    }
  }

  const chain = result?.downstream?.downstream;

  return (
    <main>
      <h1>Sandbox Routing POC</h1>
      <p className="lead">
        The browser sends one header. Every service calls the same hostnames. Istio decides
        which version answers.
      </p>

      <div className="controls">
        {SCENARIOS.map((item) => (
          <button
            key={item.id}
            onClick={() => send(item)}
            disabled={loading}
            className={scenario.id === item.id ? "active" : ""}
          >
            {item.label}
          </button>
        ))}
      </div>

      {loading && <p className="status">Calling service-a…</p>}

      {chain && (
        <>
          <div className="summary">
            <div>
              <span>propagated sandbox id</span>
              <code>{result.sandbox_id ?? "none"}</code>
            </div>
            <div>
              <span>service-c answered</span>
              <Badge version={versionOf(chain.c)} />
            </div>
            <div>
              <span>service-e answered</span>
              <Badge version={versionOf(chain.e)} />
            </div>
            <div>
              <span>service-d answered</span>
              <Badge version={versionOf(chain.d)} />
            </div>
          </div>

          <div className="grid">
            <ServiceCard name="c" node={chain.c} />
            <ServiceCard name="e" node={chain.e} />
            <ServiceCard name="d" node={chain.d} />
          </div>
        </>
      )}

      {result?.error && <pre className="error">{result.error}</pre>}
    </main>
  );
}
