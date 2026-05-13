// Server-side fetch helpers for the promptwall read API.
// The dev server proxies /api/* to the FastAPI backend via next.config.ts
// rewrites, so these fetches work the same in dev and prod (behind a
// single reverse proxy).

export type RequestSummary = {
  id: string;
  request_hash: string;
  model: string;
  latency_ms: number;
  status: number | null;
  action: string | null;
  created_at: string;
};

export type RequestListResponse = {
  items: RequestSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type DetectorSnapshot = {
  detector: string;
  score: number;
  matched: boolean;
  spans?: Array<{ start: number; end: number; label: string | null }>;
  metadata?: Record<string, unknown>;
  latency_ms: number;
  degraded: boolean;
};

export type PolicyDecision = {
  action: string;
  reason: string | null;
  matched_rule_index: number | null;
  degraded_detectors: string[];
};

export type RequestDetail = {
  id: string;
  request_hash: string;
  model: string;
  latency_ms: number;
  status: number | null;
  created_at: string;
  detector_results: DetectorSnapshot[] | null;
  policy_decision: PolicyDecision | null;
};

// Server-side fetches go directly to the API; browsers go through the rewrite.
const API_BASE =
  typeof window === "undefined"
    ? (process.env.PROMPTWALL_API_URL ?? "http://localhost:8000")
    : "";

export async function fetchRequests(limit = 50, offset = 0): Promise<RequestListResponse> {
  const url = `${API_BASE}/api/requests?limit=${limit}&offset=${offset}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`failed to fetch requests: ${res.status}`);
  }
  return res.json();
}

export async function fetchRequest(id: string): Promise<RequestDetail | null> {
  const url = `${API_BASE}/api/requests/${id}`;
  const res = await fetch(url, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(`failed to fetch request ${id}: ${res.status}`);
  }
  return res.json();
}
