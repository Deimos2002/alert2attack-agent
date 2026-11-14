import type { ReactNode } from "react";
import type { Severity, Verdict } from "../lib/api";

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-edge bg-panel ${className}`}>{children}</section>;
}

export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 px-5 pt-4 pb-2">
      <h2 className="text-sm font-semibold text-text">{children}</h2>
      {aside ? <span className="text-xs text-dim">{aside}</span> : null}
    </div>
  );
}

const SEVERITY_DOT: Record<Severity, string> = {
  critical: "bg-malicious",
  high: "bg-malicious",
  medium: "bg-suspicious",
  low: "bg-unknown",
};

const SEVERITY_TEXT: Record<Severity, string> = {
  critical: "text-malicious",
  high: "text-malicious",
  medium: "text-suspicious",
  low: "text-unknown",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium capitalize ${SEVERITY_TEXT[severity]}`}>
      <span
        aria-hidden
        className={`size-2 rounded-full ${SEVERITY_DOT[severity]} ${severity === "critical" ? "ring-2 ring-malicious/30" : ""}`}
      />
      {severity}
    </span>
  );
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  malicious: "Malicious",
  suspicious: "Suspicious",
  likely_benign: "Likely benign",
  not_enough_evidence: "Not enough evidence",
};

export const VERDICT_TONE: Record<Verdict, { text: string; bg: string; border: string; bar: string }> = {
  malicious: { text: "text-malicious", bg: "bg-malicious/10", border: "border-malicious/35", bar: "bg-malicious" },
  suspicious: { text: "text-suspicious", bg: "bg-suspicious/10", border: "border-suspicious/35", bar: "bg-suspicious" },
  likely_benign: { text: "text-benign", bg: "bg-benign/10", border: "border-benign/35", bar: "bg-benign" },
  not_enough_evidence: { text: "text-unknown", bg: "bg-unknown/10", border: "border-unknown/35", bar: "bg-unknown" },
};

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const tone = VERDICT_TONE[verdict];
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${tone.text} ${tone.bg} ${tone.border}`}
    >
      {VERDICT_LABEL[verdict]}
    </span>
  );
}

/**
 * A citation. Clicking it is the point of the whole console: every claim the
 * agent makes points at something a human can open and check.
 */
export function EvidenceChip({
  evidenceId,
  onOpen,
}: {
  evidenceId: string;
  onOpen: (id: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(evidenceId)}
      title={`Open ${evidenceId}`}
      className="mono rounded border border-accent/25 bg-accent/10 px-1.5 py-0.5 text-[11px] text-accent transition duration-150 hover:border-accent/60 hover:bg-accent/20 active:translate-y-px"
    >
      {evidenceId}
    </button>
  );
}

export function EvidenceChips({ ids, onOpen }: { ids: string[]; onOpen: (id: string) => void }) {
  if (ids.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-1.5">
      {ids.map((id) => (
        <EvidenceChip key={id} evidenceId={id} onOpen={onOpen} />
      ))}
    </div>
  );
}

/** Placeholder rows shaped like the content they stand in for. */
export function Skeleton({ rows = 3, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-3 p-5">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton h-4" style={{ width: `${88 - i * 14}%` }} />
      ))}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return <Skeleton rows={2} label={label} />;
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="rounded-lg border border-malicious/35 bg-malicious/10 px-4 py-3 text-sm text-malicious">
      {message}
    </div>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="px-6 py-12 text-center">
      <p className="text-sm font-medium text-text">{title}</p>
      {hint ? <p className="mx-auto mt-1 max-w-sm text-sm text-dim">{hint}</p> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

/** "2023-07-19T19:20:10Z" as "2023-07-19 19:20:10" (UTC, as the telemetry records it). */
export function utc(ts: string): string {
  return ts.replace("T", " ").slice(0, 19);
}
