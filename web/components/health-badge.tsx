import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

/**
 * NFR-8 made visible: when the provider is misconfigured the model-backed
 * screens can't work, but the rest of the app can, so the state belongs in the
 * header rather than as a failure on each screen. Reports presence of a key
 * only — never any part of its value (SEC-3).
 */
export async function HealthBadge() {
  try {
    const health = await api.health();
    if (health.status === "ok") {
      return (
        <Badge tone="green" title={`${health.provider} · ${health.model}`}>
          {health.model}
        </Badge>
      );
    }
    const reason = !health.database
      ? "database unreachable"
      : `no API key for ${health.provider}`;
    return (
      <Badge tone="amber" title={reason}>
        Degraded: {reason}
      </Badge>
    );
  } catch {
    return <Badge tone="red">API offline</Badge>;
  }
}
