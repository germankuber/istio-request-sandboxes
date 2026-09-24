import { useState } from "react";
import { createSandbox } from "../api";
import type {
  EnvVarRequest,
  ExternalHostResponse,
  HttpMethod,
  RuleBody,
  SandboxCreateRequest,
  ServiceCreateRequest,
  ServiceInfo,
} from "../types";
import { METHODS } from "../types";

interface EnvRow {
  name: string;
  value: string;
}

interface ServiceSelection {
  image: string;
  useMigratedDb: boolean;
  env: EnvRow[];
}

interface MockDraft {
  host: string;
  method: HttpMethod;
  path: string;
  status: number | string;
  body: string;
}

interface NewSandboxFormProps {
  services: ServiceInfo[];
  externals: ExternalHostResponse[];
  onCreated: () => Promise<void>;
}

export function NewSandboxForm({ services, externals, onCreated }: NewSandboxFormProps) {
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<Record<string, ServiceSelection>>({});
  const [mocks, setMocks] = useState<MockDraft[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function toggleService(serviceName: string) {
    setSelected((previous) => {
      const next = { ...previous };
      if (next[serviceName]) {
        delete next[serviceName];
      } else {
        next[serviceName] = { image: "", useMigratedDb: false, env: [] };
      }
      return next;
    });
  }

  function updateSelected(serviceName: string, updater: (current: ServiceSelection) => ServiceSelection) {
    setSelected((previous) => {
      const current = previous[serviceName];
      if (!current) return previous;
      return { ...previous, [serviceName]: updater(current) };
    });
  }

  function updateServiceField(serviceName: string, field: "image" | "useMigratedDb", value: string | boolean) {
    updateSelected(serviceName, (current) => ({ ...current, [field]: value }));
  }

  function addEnvRow(serviceName: string) {
    updateSelected(serviceName, (current) => ({
      ...current,
      env: [...current.env, { name: "", value: "" }],
    }));
  }

  function updateEnvRow(serviceName: string, index: number, field: keyof EnvRow, value: string) {
    updateSelected(serviceName, (current) => ({
      ...current,
      env: current.env.map((row, i) => (i === index ? { ...row, [field]: value } : row)),
    }));
  }

  function addMockRow() {
    setMocks((previous) => [
      ...previous,
      { host: externals[0]?.id ?? "external-payments", method: "POST", path: "/charge", status: 402, body: "" },
    ]);
  }

  function updateMockRow(index: number, field: keyof MockDraft, value: string) {
    setMocks((previous) => previous.map((row, i) => (i === index ? { ...row, [field]: value } : row)));
  }

  function removeMockRow(index: number) {
    setMocks((previous) => previous.filter((_, i) => i !== index));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const servicesPayload: ServiceCreateRequest[] = Object.entries(selected).map(([serviceName, config]) => ({
        name: serviceName,
        image: config.image.trim().length > 0 ? config.image.trim() : null,
        use_migrated_db: config.useMigratedDb,
        env: config.env
          .filter((row) => row.name.trim().length > 0)
          .map((row): EnvVarRequest => ({ name: row.name.trim(), value: row.value })),
      }));
      const mocksPayload: SandboxCreateRequest["mocks"] = mocks.map((mock) => ({
        host: mock.host,
        method: mock.method,
        path: mock.path,
        status: Number(mock.status),
        body: mock.body.trim().length > 0 ? (JSON.parse(mock.body) as RuleBody) : null,
        enabled: true,
      }));
      await createSandbox({ name: name.trim(), services: servicesPayload, mocks: mocksPayload });
      setName("");
      setSelected({});
      setMocks([]);
      await onCreated();
    } catch (cause) {
      setError(String(cause));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="rule-form" onSubmit={handleSubmit}>
      <div className="rule-form-row">
        <label>
          name
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="my-sandbox"
            required
          />
        </label>
      </div>

      <div className="sandbox-services">
        {services.map((service) => {
          const config = selected[service.name];
          return (
            <div key={service.name} className="sandbox-service-row">
              <label className="sandbox-service-toggle">
                <input
                  type="checkbox"
                  checked={Boolean(config)}
                  onChange={() => toggleService(service.name)}
                />
                {service.name}
              </label>
              {config && (
                <div className="sandbox-service-config">
                  <label>
                    image override
                    <input
                      value={config.image}
                      onChange={(event) => updateServiceField(service.name, "image", event.target.value)}
                      placeholder={`${service.name}:latest`}
                    />
                  </label>
                  {service.uses_db && (
                    <label className="sandbox-service-toggle">
                      <input
                        type="checkbox"
                        checked={config.useMigratedDb}
                        onChange={(event) =>
                          updateServiceField(service.name, "useMigratedDb", event.target.checked)
                        }
                      />
                      use migrated DB
                    </label>
                  )}
                  <div className="env-rows">
                    {config.env.map((row, index) => (
                      <div key={index} className="env-row">
                        <input
                          placeholder="ENV_NAME"
                          value={row.name}
                          onChange={(event) => updateEnvRow(service.name, index, "name", event.target.value)}
                        />
                        <input
                          placeholder="value"
                          value={row.value}
                          onChange={(event) => updateEnvRow(service.name, index, "value", event.target.value)}
                        />
                      </div>
                    ))}
                    <button type="button" onClick={() => addEnvRow(service.name)}>
                      + env var
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
        {services.length === 0 && <p className="status">no sandboxable services found</p>}
      </div>

      <div className="sandbox-mocks">
        <span>initial mocks</span>
        {mocks.map((mock, index) => (
          <div key={index} className="rule-form-row">
            <select value={mock.host} onChange={(event) => updateMockRow(index, "host", event.target.value)}>
              {(externals.length > 0 ? externals : [{ id: "external-payments" }, { id: "external-weather" }]).map(
                (external) => (
                  <option key={external.id} value={external.id}>
                    {external.id}
                  </option>
                )
              )}
            </select>
            <select
              value={mock.method}
              onChange={(event) => updateMockRow(index, "method", event.target.value as HttpMethod)}
            >
              {METHODS.map((method) => (
                <option key={method} value={method}>
                  {method}
                </option>
              ))}
            </select>
            <input
              placeholder="/path"
              value={mock.path}
              onChange={(event) => updateMockRow(index, "path", event.target.value)}
            />
            <input
              type="number"
              value={mock.status}
              onChange={(event) => updateMockRow(index, "status", event.target.value)}
            />
            <input
              placeholder='{"key": "value"}'
              value={mock.body}
              onChange={(event) => updateMockRow(index, "body", event.target.value)}
            />
            <button type="button" onClick={() => removeMockRow(index)}>
              remove
            </button>
          </div>
        ))}
        <button type="button" onClick={addMockRow}>
          + mock
        </button>
      </div>

      {error && <pre className="error">{error}</pre>}

      <button type="submit" disabled={submitting || name.trim().length === 0}>
        {submitting ? "creating…" : "create sandbox"}
      </button>
    </form>
  );
}
