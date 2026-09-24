import { useEffect, useRef, useState } from "react";
import { deleteSandbox, fetchChain, listExternals, listSandboxes, listServices } from "../api";
import type { ChainResult, ExternalHostResponse, SandboxSummary, ServiceInfo } from "../types";
import { DELETING_PHASE, TRANSIENT_PHASES } from "../types";
import { ConfirmDeleteModal } from "./ConfirmDeleteModal";
import { NewSandboxForm } from "./NewSandboxForm";
import { SandboxRow } from "./SandboxRow";

const REFRESH_MS = 3000;

interface SandboxesProps {
  onOpenMocks: (sandboxId: string) => void;
}

interface TryItState {
  loading: boolean;
  result: ChainResult | null;
}

export default function Sandboxes({ onOpenMocks }: SandboxesProps) {
  const [sandboxes, setSandboxes] = useState<SandboxSummary[]>([]);
  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [externals, setExternals] = useState<ExternalHostResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null);
  const [tryItState, setTryItState] = useState<Record<string, TryItState>>({});
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function refresh() {
    try {
      setSandboxes(await listSandboxes());
      setError(null);
    } catch (cause) {
      setError(String(cause));
    }
  }

  useEffect(() => {
    (async () => {
      try {
        const [servicesResult, externalsResult] = await Promise.all([listServices(), listExternals()]);
        setServices(servicesResult);
        setExternals(externalsResult);
      } catch (cause) {
        setError(String(cause));
      }
    })();
    refresh();
  }, []);

  useEffect(() => {
    const hasPending = sandboxes.some((sandbox) => TRANSIENT_PHASES.includes(sandbox.phase));
    if (hasPending && !intervalRef.current) {
      intervalRef.current = setInterval(refresh, REFRESH_MS);
    } else if (!hasPending && intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [sandboxes]);

  async function handleDelete(name: string) {
    setConfirmingDelete(null);
    setError(null);
    setSandboxes((previous) =>
      previous.map((sandbox) => (sandbox.name === name ? { ...sandbox, phase: DELETING_PHASE } : sandbox))
    );
    try {
      await deleteSandbox(name);
    } catch (cause) {
      setError(String(cause));
    }
    await refresh();
  }

  async function handleTryIt(name: string) {
    setTryItState((previous) => ({ ...previous, [name]: { loading: true, result: null } }));
    try {
      const result = await fetchChain(name);
      setTryItState((previous) => ({ ...previous, [name]: { loading: false, result } }));
    } catch (cause) {
      setTryItState((previous) => ({
        ...previous,
        [name]: { loading: false, result: { error: String(cause) } },
      }));
    }
  }

  return (
    <section className="mocks">
      <NewSandboxForm services={services} externals={externals} onCreated={refresh} />

      {error && <pre className="error">{error}</pre>}

      <table className="rule-table">
        <thead>
          <tr>
            <th>name</th>
            <th>phase</th>
            <th>services</th>
            <th>mocks</th>
            <th>age</th>
            <th>actions</th>
          </tr>
        </thead>
        <tbody>
          {sandboxes.map((sandbox) => (
            <SandboxRow
              key={sandbox.name}
              sandbox={sandbox}
              onOpenMocks={onOpenMocks}
              onTryIt={handleTryIt}
              tryItResult={tryItState[sandbox.name]?.result}
              tryItLoading={Boolean(tryItState[sandbox.name]?.loading)}
              onRequestDelete={setConfirmingDelete}
            />
          ))}
          {sandboxes.length === 0 && (
            <tr>
              <td colSpan={6} className="rule-empty">
                no sandboxes yet
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {confirmingDelete && (
        <ConfirmDeleteModal
          name={confirmingDelete}
          onConfirm={handleDelete}
          onCancel={() => setConfirmingDelete(null)}
        />
      )}
    </section>
  );
}
