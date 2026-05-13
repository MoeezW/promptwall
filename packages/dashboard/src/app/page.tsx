import Link from "next/link";

import { fetchRequests } from "@/lib/api";

export const dynamic = "force-dynamic";

function countAction(items: Array<{ action: string | null }>, action: string): number {
  return items.filter((i) => i.action === action).length;
}

export default async function Home() {
  let total = 0;
  let blocks = 0;
  let redacts = 0;
  let allows = 0;
  let error: string | null = null;

  try {
    const response = await fetchRequests(200, 0);
    total = response.total;
    blocks = countAction(response.items, "block");
    redacts = countAction(response.items, "redact");
    allows = countAction(response.items, "allow");
  } catch (e) {
    error = e instanceof Error ? e.message : "unknown error";
  }

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <header className="mb-10">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">
          promptwall
        </h1>
        <p className="mt-2 text-sm text-slate-600">
          Self-hosted LLM safety gateway. Detector pipeline, policy engine,
          and reversible PII redaction in front of every request.
        </p>
      </header>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-800">
          <p className="font-semibold">API not reachable</p>
          <p className="mt-1">
            Cannot load summary from <code className="font-mono">/api/requests</code>:{" "}
            {error}
          </p>
          <p className="mt-2 text-xs text-red-700">
            Is the proxy running on{" "}
            <code className="font-mono">localhost:8000</code>? Start it with{" "}
            <code className="font-mono">make serve</code>.
          </p>
        </div>
      ) : (
        <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Stat label="Total requests" value={total.toString()} />
          <Stat label="Blocked" value={blocks.toString()} accent="red" />
          <Stat label="Redacted" value={redacts.toString()} accent="amber" />
          <Stat label="Allowed" value={allows.toString()} accent="emerald" />
        </section>
      )}

      <section className="mt-10 rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
        <h2 className="text-lg font-semibold text-slate-900">Next steps</h2>
        <ul className="mt-4 space-y-3 text-sm text-slate-700">
          <li>
            <Link
              href="/requests"
              className="font-medium text-blue-600 hover:underline"
            >
              View all requests →
            </Link>{" "}
            — paginated list with action badges, click any row for the
            decision tree.
          </li>
          <li>
            <a
              href="http://localhost:16686"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-blue-600 hover:underline"
            >
              Open Jaeger →
            </a>{" "}
            — distributed traces for every proxied request, named{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">
              proxy.chat.completions
            </code>
            .
          </li>
          <li>
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-blue-600 hover:underline"
            >
              Browse the API →
            </a>{" "}
            — FastAPI's auto-generated docs for{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs">
              POST /v1/chat/completions
            </code>{" "}
            and the dashboard read endpoints.
          </li>
        </ul>
      </section>
    </main>
  );
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "red" | "amber" | "emerald";
}) {
  const tones: Record<string, string> = {
    red: "text-red-700",
    amber: "text-amber-700",
    emerald: "text-emerald-700",
  };
  const tone = accent ? tones[accent] : "text-slate-900";
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-2 text-3xl font-semibold ${tone}`}>{value}</div>
    </div>
  );
}
