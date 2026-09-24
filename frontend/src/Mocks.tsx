import { useEffect, useState } from "react";
import { createRule, deleteRule, listExternals, listRules, toggleRule } from "./api";
import type { ExternalHostId, ExternalHostResponse, HttpMethod, Rule, RuleBody } from "./types";
import { METHODS } from "./types";

interface RuleFormState {
  sandbox_id: string;
  host: string;
  method: HttpMethod;
  path: string;
  status: number | string;
  delay_ms: number | string;
  body: string;
}

const EMPTY_FORM: RuleFormState = {
  sandbox_id: "test-123",
  host: "external-payments",
  method: "POST",
  path: "/charge",
  status: 402,
  delay_ms: 0,
  body: '{\n  "error": "card_declined"\n}',
};

interface RuleRowProps {
  rule: Rule;
  onToggle: (id: string) => void;
  onDelete: (id: string) => void;
}

function RuleRow({ rule, onToggle, onDelete }: RuleRowProps) {
  return (
    <tr>
      <td>{rule.enabled ? "on" : "off"}</td>
      <td>{rule.sandbox_id}</td>
      <td>{rule.host}</td>
      <td>{rule.method}</td>
      <td>{rule.path}</td>
      <td>{rule.status}</td>
      <td className="rule-actions">
        <button onClick={() => onToggle(rule.id)}>{rule.enabled ? "disable" : "enable"}</button>
        <button onClick={() => onDelete(rule.id)}>delete</button>
      </td>
    </tr>
  );
}

interface MocksProps {
  initialSandboxId?: string | null;
}

export default function Mocks({ initialSandboxId = null }: MocksProps) {
  const [externals, setExternals] = useState<ExternalHostResponse[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [form, setForm] = useState<RuleFormState>(EMPTY_FORM);
  const [filter, setFilter] = useState(initialSandboxId ?? "");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setError(null);
    try {
      const trimmedFilter = filter.trim();
      const [externalsResult, rulesResult] = await Promise.all([
        listExternals(),
        listRules(trimmedFilter.length > 0 ? trimmedFilter : undefined),
      ]);
      setExternals(externalsResult);
      setRules(rulesResult);
    } catch (cause) {
      setError(String(cause));
    }
  }

  useEffect(() => {
    refresh();
  }, [filter]);

  function updateField<K extends keyof RuleFormState>(field: K, value: RuleFormState[K]) {
    setForm((previous) => ({ ...previous, [field]: value }));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      let body: RuleBody = null;
      if (form.body.trim().length > 0) {
        body = JSON.parse(form.body) as RuleBody;
      }
      await createRule({
        sandbox_id: form.sandbox_id,
        host: form.host as ExternalHostId,
        method: form.method,
        path: form.path,
        status: Number(form.status),
        delay_ms: Number(form.delay_ms),
        headers: {},
        body,
        enabled: true,
      });
      setForm(EMPTY_FORM);
      await refresh();
    } catch (cause) {
      setError(String(cause));
    } finally {
      setLoading(false);
    }
  }

  async function handleToggle(id: string) {
    setError(null);
    try {
      await toggleRule(id);
      await refresh();
    } catch (cause) {
      setError(String(cause));
    }
  }

  async function handleDelete(id: string) {
    setError(null);
    try {
      await deleteRule(id);
      await refresh();
    } catch (cause) {
      setError(String(cause));
    }
  }

  return (
    <section className="mocks">
      <label className="rule-filter">
        filter by sandbox
        <input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="all sandboxes"
        />
      </label>

      <form className="rule-form" onSubmit={handleSubmit}>
        <div className="rule-form-row">
          <label>
            sandbox id
            <input
              value={form.sandbox_id}
              onChange={(event) => updateField("sandbox_id", event.target.value)}
              required
            />
          </label>
          <label>
            host
            <select value={form.host} onChange={(event) => updateField("host", event.target.value)}>
              {(externals.length > 0
                ? externals
                : [{ id: "external-payments" }, { id: "external-weather" }]
              ).map((external) => (
                <option key={external.id} value={external.id}>
                  {external.id}
                </option>
              ))}
            </select>
          </label>
          <label>
            method
            <select
              value={form.method}
              onChange={(event) => updateField("method", event.target.value as HttpMethod)}
            >
              {METHODS.map((method) => (
                <option key={method} value={method}>
                  {method}
                </option>
              ))}
            </select>
          </label>
          <label>
            path
            <input
              value={form.path}
              onChange={(event) => updateField("path", event.target.value)}
              required
            />
          </label>
          <label>
            status
            <input
              type="number"
              value={form.status}
              onChange={(event) => updateField("status", event.target.value)}
            />
          </label>
          <label>
            delay ms
            <input
              type="number"
              value={form.delay_ms}
              onChange={(event) => updateField("delay_ms", event.target.value)}
            />
          </label>
        </div>
        <label className="rule-form-body">
          response body (JSON)
          <textarea
            value={form.body}
            onChange={(event) => updateField("body", event.target.value)}
            rows={5}
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "creating…" : "create rule"}
        </button>
      </form>

      {error && <pre className="error">{error}</pre>}

      <table className="rule-table">
        <thead>
          <tr>
            <th>enabled</th>
            <th>sandbox</th>
            <th>host</th>
            <th>method</th>
            <th>path</th>
            <th>status</th>
            <th>actions</th>
          </tr>
        </thead>
        <tbody>
          {rules.map((rule) => (
            <RuleRow key={rule.id} rule={rule} onToggle={handleToggle} onDelete={handleDelete} />
          ))}
          {rules.length === 0 && (
            <tr>
              <td colSpan={7} className="rule-empty">
                no rules yet
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
