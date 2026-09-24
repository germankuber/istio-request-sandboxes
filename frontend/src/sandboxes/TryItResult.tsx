import { MockBadge } from "../components/MockBadge";
import { VersionBadge } from "../components/VersionBadge";
import type { ChainResult } from "../types";
import { isChainErrorNode, isChainResponse } from "../types";

interface TryItResultProps {
  result: ChainResult | null;
}

export function TryItResult({ result }: TryItResultProps) {
  if (!result) return null;
  if ("error" in result) return <pre className="error">{result.error}</pre>;
  if (!isChainResponse(result)) return null;
  const chain = result.downstream?.downstream;
  if (!chain) return null;
  return (
    <div className="try-it-result">
      {(["c", "e", "d"] as const).map((key) => {
        const node = chain[key];
        const version = !isChainErrorNode(node) ? node.version : null;
        const external = node && "external" in node ? node.external : undefined;
        return (
          <div key={key} className="try-it-row">
            <span>service-{key}</span>
            <VersionBadge version={version} />
            {key === "d" && external && (
              <span className="try-it-externals">
                <span>
                  payments <MockBadge mocked={external.payments.mocked} />
                </span>
                <span>
                  weather <MockBadge mocked={external.weather.mocked} />
                </span>
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
