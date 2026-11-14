import { Panel, SectionTitle } from "../components/ui";
import type { Phase } from "../lib/api";
import type { TraceState } from "../lib/useInvestigationStream";

const RAIL: { phase: Phase; label: string; hint: string }[] = [
  { phase: "plan", label: "Plan", hint: "Sketch hypotheses and first questions" },
  { phase: "investigate", label: "Investigate", hint: "Fetch telemetry through tools only" },
  { phase: "ground", label: "Ground", hint: "Search ATT&CK with the fetched evidence" },
  { phase: "write", label: "Write", hint: "Fill the case file from the evidence ledger" },
  { phase: "verify", label: "Verify", hint: "Check every citation, no model involved" },
  { phase: "repair", label: "Repair", hint: "Fix or strip claims that failed" },
  { phase: "levers", label: "Safety rules", hint: "Deterministic checks on the verdict" },
];

const STATUS_LABEL: Record<TraceState["status"], string> = {
  idle: "Idle",
  connecting: "Connecting",
  streaming: "Running",
  done: "Finished",
  error: "Failed",
};

function StepRail({ trace }: { trace: TraceState }) {
  return (
    <ol className="px-5 pb-4">
      {RAIL.map(({ phase, label, hint }, i) => {
        const active = trace.phase === phase && trace.status === "streaming";
        const seen = trace.phasesSeen.includes(phase);
        const last = i === RAIL.length - 1;
        return (
          <li key={phase} className="relative flex gap-3 pb-3 last:pb-0">
            {last ? null : (
              <span aria-hidden className={`absolute top-5 left-[7px] h-full w-px ${seen ? "bg-benign/40" : "bg-edge"}`} />
            )}
            <span
              aria-hidden
              className={`relative mt-1 size-[15px] shrink-0 rounded-full border-2 ${
                active
                  ? "animate-pulse border-accent bg-accent/30"
                  : seen
                    ? "border-benign bg-benign"
                    : "border-edge bg-panel"
              }`}
            />
            <div className="min-w-0">
              <div className={`text-sm ${active ? "font-medium text-accent" : seen ? "text-text" : "text-dim/70"}`}>
                {label}
                {active ? <span className="ml-2 text-xs font-normal text-dim">in progress</span> : null}
              </div>
              <div className="text-xs text-dim/80">{hint}</div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/**
 * The deterministic post-write controls.
 *
 * A lever that declined to fire is shown, not hidden. On a benign LSASS alert
 * the interesting fact is that the ceiling looked at it and acted — and on a
 * real attack, that it looked and let it through.
 */
function Levers({ trace }: { trace: TraceState }) {
  if (trace.levers.length === 0) return null;
  return (
    <div className="border-t border-edge px-5 py-3">
      <div className="label mb-2">Safety rules applied</div>
      <ul className="space-y-1.5">
        {trace.levers.map((lever, i) => (
          <li key={`${lever.lever_id}-${i}`} className="flex items-baseline justify-between gap-3 text-xs">
            <span className="mono text-text">{lever.lever_id}</span>
            <span className={lever.fired ? "text-right text-suspicious" : "text-dim/70"}>
              {lever.fired ? (lever.effect ?? "changed the verdict") : "checked, no change"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function TraceView({ trace }: { trace: TraceState }) {
  const llmMs = trace.llmCalls.reduce((sum, c) => sum + c.duration_ms, 0);
  const uniqueEvidence = new Set(trace.ledger.map((l) => l.evidence_id)).size;
  const running = trace.status === "streaming" || trace.status === "connecting";

  return (
    <Panel className="rise overflow-hidden">
      <SectionTitle
        aside={
          <span className={`inline-flex items-center gap-1.5 ${trace.status === "error" ? "text-malicious" : ""}`} aria-live="polite">
            {running ? <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-accent" /> : null}
            {STATUS_LABEL[trace.status]}
          </span>
        }
      >
        Live run
      </SectionTitle>

      <StepRail trace={trace} />

      <dl className="grid grid-cols-4 border-t border-edge text-center">
        {[
          ["Tools", trace.toolCalls.length],
          ["Model calls", trace.llmCalls.length],
          ["Evidence", uniqueEvidence],
          ["Model time", `${(llmMs / 1000).toFixed(1)}s`],
        ].map(([label, value]) => (
          <div key={label} className="border-r border-edge px-2 py-3 last:border-0">
            <dt className="label">{label}</dt>
            <dd className="mono mt-0.5 text-sm font-medium">{value}</dd>
          </div>
        ))}
      </dl>

      <Levers trace={trace} />

      {trace.verification ? (
        <div
          className={`border-t border-edge px-5 py-3 text-xs ${
            trace.verification.status === "degraded" ? "text-suspicious" : "text-benign"
          }`}
        >
          Citations {trace.verification.status}
          {trace.verification.stripped_claims > 0 ? ` · ${trace.verification.stripped_claims} claim(s) stripped` : ""}
          {trace.verification.repairs_used > 0 ? ` · ${trace.verification.repairs_used} repair(s)` : ""}
        </div>
      ) : null}

      {trace.error ? (
        <div role="alert" className="border-t border-malicious/35 bg-malicious/10 px-5 py-3 text-xs text-malicious">
          {trace.error}
        </div>
      ) : null}

      {trace.toolCalls.length > 0 ? (
        <div className="max-h-72 overflow-y-auto border-t border-edge">
          <div className="label px-5 pt-3 pb-1">Tool calls</div>
          <ol className="px-5 pb-3">
            {trace.toolCalls.map((call) => (
              <li key={call.seq} className="flex items-baseline gap-2 border-b border-edge/40 py-1.5 text-xs last:border-0">
                <span className="mono w-6 shrink-0 text-dim/70">{call.call_seq}</span>
                <span className="min-w-0 flex-1">
                  <span className="mono text-text">{call.tool}</span>
                  <span className="mono block truncate text-[11px] text-dim/80" title={call.args_digest}>
                    {call.args_digest}
                  </span>
                </span>
                {call.ok ? (
                  <span className="mono shrink-0 text-dim">{call.evidence_ids.length} ev</span>
                ) : (
                  // A failed tool is data the agent handled, not a crash.
                  <span className="shrink-0 text-suspicious" title={call.error ?? ""}>
                    no result
                  </span>
                )}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
    </Panel>
  );
}
