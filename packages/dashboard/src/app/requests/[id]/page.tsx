import Link from "next/link";
import { notFound } from "next/navigation";

import { ScoreChart } from "@/components/score-chart";
import { fetchRequest } from "@/lib/api";

export const dynamic = "force-dynamic";

type Params = { id: string };

function actionBadge(action: string | null | undefined): string {
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

export default async function RequestDetailPage({
  params,
}: {
  params: Promise<Params>;
}) {
  const { id } = await params;
  const detail = await fetchRequest(id);
  if (!detail) notFound();

  const decision = detail.policy_decision;
  const detectors = detail.detector_results ?? [];

  return (
    <main className="mx-auto max-w-5xl px-6 py-10 space-y-6">
      <nav className="text-sm">
        <Link href="/requests" className="text-blue-600 hover:underline">
          ← back to requests
        </Link>
      </nav>

      <header className="space-y-2">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold text-slate-900">Request detail</h1>
          <span
            className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${actionBadge(
              decision?.action,
            )}`}
          >
            {decision?.action ?? "—"}
          </span>
        </div>
        <p className="font-mono text-xs text-slate-500">
          {detail.request_hash}
        </p>
      </header>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Tile label="Model" value={detail.model} mono />
        <Tile label="Status" value={detail.status?.toString() ?? "—"} />
        <Tile label="Latency" value={`${detail.latency_ms.toFixed(1)} ms`} />
        <Tile label="When" value={new Date(detail.created_at).toLocaleString()} />
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-base font-semibold text-slate-900">Policy decision</h2>
        {decision ? (
          <dl className="mt-3 grid grid-cols-1 gap-2 text-sm md:grid-cols-2">
            <Row label="Action" value={decision.action} />
            <Row
              label="Matched rule index"
              value={
                decision.matched_rule_index === null
                  ? "—"
                  : decision.matched_rule_index.toString()
              }
            />
            <Row
              label="Reason"
              value={decision.reason ?? "—"}
              className="md:col-span-2"
            />
            {decision.degraded_detectors.length > 0 ? (
              <Row
                label="Degraded detectors"
                value={decision.degraded_detectors.join(", ")}
                className="md:col-span-2"
              />
            ) : null}
          </dl>
        ) : (
          <p className="mt-3 text-sm text-slate-500">
            No decision recorded (request predates the persistence migration).
          </p>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-base font-semibold text-slate-900">Detector scores</h2>
        {detectors.length > 0 ? (
          <>
            <ScoreChart results={detectors} />
            <div className="mt-4 overflow-hidden rounded border border-slate-100">
              <table className="min-w-full divide-y divide-slate-100 text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2">Detector</th>
                    <th className="px-3 py-2">Score</th>
                    <th className="px-3 py-2">Matched</th>
                    <th className="px-3 py-2">Latency</th>
                    <th className="px-3 py-2">Notes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {detectors.map((d) => (
                    <tr key={d.detector}>
                      <td className="px-3 py-2 font-mono text-xs">{d.detector}</td>
                      <td className="px-3 py-2">{d.score.toFixed(3)}</td>
                      <td className="px-3 py-2">{d.matched ? "yes" : "no"}</td>
                      <td className="px-3 py-2">{d.latency_ms.toFixed(1)} ms</td>
                      <td className="px-3 py-2 text-xs text-slate-500">
                        {d.degraded
                          ? `degraded${
                              d.metadata && (d.metadata as Record<string, unknown>).reason
                                ? `: ${(d.metadata as Record<string, unknown>).reason}`
                                : ""
                            }`
                          : (d.spans?.length ?? 0) > 0
                          ? `${d.spans!.length} span(s)`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="mt-3 text-sm text-slate-500">No detector results stored.</p>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm text-sm text-slate-500">
        <p>
          Distributed traces for this request live in Jaeger; filter by{" "}
          <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">
            request.hash={detail.request_hash.slice(0, 16)}…
          </code>{" "}
          at{" "}
          <a
            href="http://localhost:16686"
            target="_blank"
            rel="noreferrer"
            className="text-blue-600 hover:underline"
          >
            localhost:16686
          </a>
          .
        </p>
      </section>
    </main>
  );
}

function Tile({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div
        className={`mt-1 text-sm text-slate-900 ${mono ? "font-mono" : ""}`}
      >
        {value}
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  className,
}: {
  label: string;
  value: string;
  className?: string;
}) {
  return (
    <div className={className}>
      <dt className="text-xs uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-1 text-sm text-slate-900">{value}</dd>
    </div>
  );
}
