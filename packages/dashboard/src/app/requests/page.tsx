import Link from "next/link";

import { fetchRequests, type RequestSummary } from "@/lib/api";

export const dynamic = "force-dynamic";

function actionStyle(action: string | null): string {
  switch (action) {
    case "block":
      return "bg-red-100 text-red-800 border-red-300";
    case "redact":
      return "bg-amber-100 text-amber-800 border-amber-300";
    case "allow":
      return "bg-emerald-100 text-emerald-800 border-emerald-300";
    default:
      return "bg-slate-100 text-slate-700 border-slate-300";
  }
}

function formatLatency(ms: number): string {
  if (ms < 10) return `${ms.toFixed(1)} ms`;
  return `${ms.toFixed(0)} ms`;
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString();
}

export default async function RequestsPage() {
  let items: RequestSummary[] = [];
  let total = 0;
  let error: string | null = null;
  try {
    const response = await fetchRequests(50, 0);
    items = response.items;
    total = response.total;
  } catch (e) {
    error = e instanceof Error ? e.message : "unknown error";
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-900">Requests</h1>
        <p className="mt-1 text-sm text-slate-600">
          {error
            ? `Could not load requests: ${error}`
            : `Showing the ${items.length} most recent of ${total} proxied requests.`}
        </p>
      </header>

      {items.length === 0 && !error ? (
        <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-12 text-center">
          <p className="text-sm text-slate-600">
            No requests yet. Send one through{" "}
            <code className="rounded bg-slate-200 px-1 py-0.5 text-xs">
              POST /v1/chat/completions
            </code>{" "}
            to populate the dashboard.
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-4 py-3 text-left font-medium text-slate-700">When</th>
                <th className="px-4 py-3 text-left font-medium text-slate-700">Model</th>
                <th className="px-4 py-3 text-left font-medium text-slate-700">Action</th>
                <th className="px-4 py-3 text-left font-medium text-slate-700">Status</th>
                <th className="px-4 py-3 text-right font-medium text-slate-700">Latency</th>
                <th className="px-4 py-3 text-left font-medium text-slate-700">Hash</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((row) => (
                <tr
                  key={row.id}
                  className="hover:bg-slate-50"
                >
                  <td className="px-4 py-3 text-slate-700">
                    <Link
                      href={`/requests/${row.id}`}
                      className="text-blue-600 hover:underline"
                    >
                      {formatTimestamp(row.created_at)}
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-700">
                    {row.model}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${actionStyle(
                        row.action,
                      )}`}
                    >
                      {row.action ?? "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-700">{row.status ?? "—"}</td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-slate-700">
                    {formatLatency(row.latency_ms)}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">
                    {row.request_hash.slice(0, 12)}…
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
