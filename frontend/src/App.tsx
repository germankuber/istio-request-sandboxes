import { useState } from "react";
import { fetchChain } from "./api";
import { MockBadge } from "./components/MockBadge";
import { VersionBadge } from "./components/VersionBadge";
import Mocks from "./Mocks";
import Sandboxes from "./sandboxes/Sandboxes";
import type { ChainNode, ChainResult } from "./types";
import { isChainErrorNode, isChainResponse } from "./types";

interface Scenario {
  id: string;
  label: string;
  sandboxId: string | null;
}

const SCENARIOS: Scenario[] = [
  { id: "none", label: "No header", sandboxId: null },
  { id: "test-123", label: "X-Sandbox-ID: test-123", sandboxId: "test-123" },
  { id: "unknown", label: "X-Sandbox-ID: unknown-id", sandboxId: "unknown-id" },
];

function versionOf(node: ChainNode | null | undefined): string | null {
  if (!node || isChainErrorNode(node)) return null;
  return node.version;
}

interface ExternalRowProps {
  name: string;
  node: { mocked?: boolean } | null | undefined;
}

function ExternalRow({ name, node }: ExternalRowProps) {
  if (!node) return null;
  return (
    <div className="external-row">
      <span>{name}</span>
      <MockBadge mocked={Boolean(node.mocked)} />
    </div>
  );
}

interface ServiceCardProps {
  name: string;
  node: ChainNode;
}

function ServiceCard({ name, node }: ServiceCardProps) {
  const version = versionOf(node);
  const external = "external" in node ? node.external : undefined;
  return (
    <div className="card">
      <div className="card-head">
        <strong>service-{name}</strong>
        <VersionBadge version={version} />
      </div>
      {external && (
        <div className="external-summary">
          <ExternalRow name="payments" node={external.payments} />
          <ExternalRow name="weather" node={external.weather} />
        </div>
      )}
      {isChainErrorNode(node) ? (
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

function ChainView() {
  const [result, setResult] = useState<ChainResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [scenario, setScenario] = useState<Scenario>(SCENARIOS[0]!);

  async function send(next: Scenario) {
    setScenario(next);
    setLoading(true);
    setResult(null);
    try {
      setResult(await fetchChain(next.sandboxId));
    } catch (error) {
      setResult({ error: String(error) });
    } finally {
      setLoading(false);
    }
  }

  const chain = isChainResponse(result) ? result.downstream?.downstream : undefined;
  const sandboxId = isChainResponse(result) ? result.sandbox_id : undefined;
  const localError = result && "error" in result ? result.error : undefined;

  return (
    <>
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
              <code>{sandboxId ?? "none"}</code>
            </div>
            <div>
              <span>service-c answered</span>
              <VersionBadge version={versionOf(chain.c)} />
            </div>
            <div>
              <span>service-e answered</span>
              <VersionBadge version={versionOf(chain.e)} />
            </div>
            <div>
              <span>service-d answered</span>
              <VersionBadge version={versionOf(chain.d)} />
            </div>
          </div>

          <div className="grid">
            <ServiceCard name="c" node={chain.c} />
            <ServiceCard name="e" node={chain.e} />
            <ServiceCard name="d" node={chain.d} />
          </div>
        </>
      )}

      {localError && <pre className="error">{localError}</pre>}
    </>
  );
}

type Tab = "sandboxes" | "chain" | "mocks";

export default function App() {
  const [tab, setTab] = useState<Tab>("sandboxes");
  const [mocksFilter, setMocksFilter] = useState<string | null>(null);

  function openMocksFor(sandboxId: string) {
    setMocksFilter(sandboxId);
    setTab("mocks");
  }

  return (
    <main>
      <h1>Sandbox Routing POC</h1>
      <p className="lead">
        The browser sends one header. Every service calls the same hostnames. Istio decides
        which version answers.
      </p>

      <div className="tabs">
        <button className={tab === "sandboxes" ? "active" : ""} onClick={() => setTab("sandboxes")}>
          Sandboxes
        </button>
        <button className={tab === "chain" ? "active" : ""} onClick={() => setTab("chain")}>
          Chain
        </button>
        <button className={tab === "mocks" ? "active" : ""} onClick={() => setTab("mocks")}>
          Mocks
        </button>
      </div>

      {tab === "sandboxes" && <Sandboxes onOpenMocks={openMocksFor} />}
      {tab === "chain" && <ChainView />}
      {tab === "mocks" && <Mocks key={mocksFilter ?? "all"} initialSandboxId={mocksFilter} />}
    </main>
  );
}
