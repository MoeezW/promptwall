"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { DetectorSnapshot } from "@/lib/api";

type Props = {
  results: DetectorSnapshot[];
};

const COLOR_MATCHED = "#dc2626"; // red-600
const COLOR_DEGRADED = "#f59e0b"; // amber-500
const COLOR_CLEAN = "#64748b"; // slate-500

function colorFor(snapshot: DetectorSnapshot): string {
  if (snapshot.degraded) return COLOR_DEGRADED;
  if (snapshot.matched) return COLOR_MATCHED;
  return COLOR_CLEAN;
}

export function ScoreChart({ results }: Props) {
  const data = results.map((r) => ({
    name: r.detector,
    score: Number(r.score.toFixed(3)),
    matched: r.matched,
    degraded: r.degraded,
  }));

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 12 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="name" tick={{ fontSize: 12 }} />
          <YAxis domain={[0, 1]} tick={{ fontSize: 12 }} />
          <Tooltip
            formatter={(value) =>
              typeof value === "number" ? value.toFixed(3) : String(value)
            }
            contentStyle={{ borderRadius: "0.375rem", fontSize: "0.75rem" }}
          />
          <Bar dataKey="score" radius={[4, 4, 0, 0]}>
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={colorFor(results[index])}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
