import { useRef, useState } from "react";
import { inUnit } from "../lib/format";

interface Part {
  name: string;
  amount: number;
  share: number;
}

/**
 * Where the money comes from: one 100% stacked bar (equity, borrowings, trade payables, the rest).
 * Series colours in fixed order from the validated palette; 2px surface gaps; 4px rounded outer ends.
 * Every segment has a hover tooltip, and the legend below is also the table of figures, so nothing is told by colour alone.
 */
export default function LiabilityBar({ parts, total, factor, unit }: { parts: Part[]; total: number; factor: number; unit: string | null }) {
  const box = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<{ x: number; part: Part; index: number } | null>(null);
  const shown = parts.map((p, index) => ({ ...p, index })).filter((p) => p.share > 0);

  return (
    <div>
      <div ref={box} className="relative" onMouseLeave={() => setTip(null)}>
        <div className="flex h-7 gap-[2px] rounded-[4px] overflow-hidden grow-x" role="img" aria-label={parts.map((p) => `${p.name} ${p.share}%`).join(", ")}>
          {shown.map((p) => (
            <div
              key={p.name}
              className="h-full transition-opacity"
              style={{ width: `${p.share}%`, background: `var(--series-${p.index + 1})`, opacity: tip && tip.index !== p.index ? 0.55 : 1 }}
              onMouseMove={(e) => {
                const r = box.current!.getBoundingClientRect();
                setTip({ x: e.clientX - r.left, part: p, index: p.index });
              }}
            />
          ))}
        </div>
        {/* Direct labels for segments wide enough to carry one; the legend carries the rest. */}
        <div className="relative h-5 mt-1 text-[11px] text-text-secondary tabular">
          {shown.reduce<{ left: number; nodes: JSX.Element[] }>((acc, p) => {
            if (p.share >= 9) acc.nodes.push(<span key={p.name} className="absolute whitespace-nowrap -translate-x-1/2" style={{ left: `${acc.left + p.share / 2}%` }}>{Math.round(p.share)}%</span>);
            acc.left += p.share;
            return acc;
          }, { left: 0, nodes: [] }).nodes}
        </div>
        {tip && (
          <div
            className="absolute -top-2 -translate-y-full -translate-x-1/2 pointer-events-none card px-3 py-2 text-xs whitespace-nowrap z-10"
            style={{ left: Math.min(Math.max(tip.x, 90), (box.current?.clientWidth ?? 0) - 90), boxShadow: "0 8px 24px rgb(var(--shadow) / 0.18)" }}
          >
            <p className="font-medium flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-sm" style={{ background: `var(--series-${tip.index + 1})` }} />
              {tip.part.name}
            </p>
            <p className="text-text-secondary tabular mt-0.5">{inUnit(tip.part.amount, factor)} {unit ? `(${unit})` : ""} · {tip.part.share}% of the balance sheet</p>
          </div>
        )}
      </div>

      <table className="w-full text-sm mt-2">
        <thead className="sr-only"><tr><th>Source</th><th>Amount</th><th>Share</th></tr></thead>
        <tbody>
          {parts.map((p, index) => (
            <tr key={p.name} className="border-t border-bg-border first:border-t-0">
              <td className="py-1.5">
                <span className="inline-flex items-center gap-2">
                  <span className="w-3 h-3 rounded-[3px] shrink-0" style={{ background: `var(--series-${index + 1})` }} aria-hidden />
                  {p.name}
                </span>
              </td>
              <td className="py-1.5 text-right tabular text-text-secondary">{inUnit(p.amount, factor)}</td>
              <td className="py-1.5 text-right tabular w-16">{p.share}%</td>
            </tr>
          ))}
          <tr className="border-t border-bg-border font-medium">
            <td className="py-1.5">Total (= total assets)</td>
            <td className="py-1.5 text-right tabular">{inUnit(total, factor)}</td>
            <td className="py-1.5 text-right tabular">100%</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
