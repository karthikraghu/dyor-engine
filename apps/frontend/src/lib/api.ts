import type {
  BuiltinBacktestRequest,
  DecisionRequest,
  DecisionResponse,
  ExecuteRequest,
  ExecuteResponse,
  ServiceHealth,
} from "@/lib/types";

export const SANDBOX_API_URL =
  process.env.NEXT_PUBLIC_SANDBOX_API_URL ?? "http://localhost:8000";

export const ORCHESTRATOR_API_URL =
  process.env.NEXT_PUBLIC_ORCHESTRATOR_API_URL ?? "http://localhost:8010";

async function readJson<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? String(payload.detail)
        : `Request failed with HTTP ${response.status}`;
    throw new Error(detail);
  }

  return payload as T;
}

async function postJson<TResponse, TBody>(
  url: string,
  body: TBody,
): Promise<TResponse> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  return readJson<TResponse>(response);
}

export async function getSandboxHealth() {
  const response = await fetch(`${SANDBOX_API_URL}/health`, {
    cache: "no-store",
  });
  return readJson<ServiceHealth>(response);
}

export async function getOrchestratorHealth() {
  const response = await fetch(`${ORCHESTRATOR_API_URL}/health`, {
    cache: "no-store",
  });
  return readJson<ServiceHealth>(response);
}

export async function requestDecision(body: DecisionRequest) {
  return postJson<DecisionResponse, DecisionRequest>(
    `${ORCHESTRATOR_API_URL}/decision`,
    body,
  );
}

export async function executeStrategy(body: ExecuteRequest) {
  return postJson<ExecuteResponse, ExecuteRequest>(
    `${SANDBOX_API_URL}/execute`,
    body,
  );
}

export async function runBuiltinBacktest(body: BuiltinBacktestRequest) {
  return postJson<ExecuteResponse, BuiltinBacktestRequest>(
    `${SANDBOX_API_URL}/backtest`,
    body,
  );
}
