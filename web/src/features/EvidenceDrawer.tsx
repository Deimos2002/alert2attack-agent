import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { ErrorBox, Skeleton } from "../components/ui";
import { ApiError, api } from "../lib/api";

function Field({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="grid grid-cols-[8rem_1fr] gap-3 border-b border-edge/50 py-2 last:border-0">
      <dt className="label pt-0.5">{label}</dt>
      <dd className="mono text-xs leading-relaxed break-all text-text">{String(value)}</dd>
    </div>
  );
}

const KIND_LABEL: Record<string, string> = {
  event: "Telemetry event",
  sigma_rule: "Detection rule",
  attack_technique: "ATT&CK technique",
};

/**
 * Resolves one citation back to the record the agent fetched.
 *
 * A 404 here is not a UI failure: the verifier is supposed to have stripped any
 * claim citing evidence outside the run's ledger, so an unresolvable citation
 * means something upstream is wrong. It is rendered loudly for that reason.
 */
export function EvidenceDrawer({
  jobId,
  evidenceId,
  onClose,
}: {
  jobId: string;
  evidenceId: string;
  onClose: () => void;
}) {
  const { data, isPending, error } = useQuery({
    queryKey: ["evidence", jobId, evidenceId],
    queryFn: () => api.evidence(jobId, evidenceId),
    retry: false,
  });
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const unverifiable = error instanceof ApiError && error.status === 404;

  return (
    <>
      <button
        type="button"
        aria-label="Close evidence"
        onClick={onClose}
        className="fixed inset-0 z-20 cursor-default bg-ink/70"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Evidence ${evidenceId}`}
        className="rise fixed inset-y-0 right-0 z-30 flex w-[34rem] max-w-full flex-col border-l border-edge bg-panel shadow-[-24px_0_48px_rgb(4_8_14/0.55)]"
      >
        <header className="flex items-start justify-between gap-3 border-b border-edge px-5 py-4">
          <div className="min-w-0">
            <div className="label">{data ? (KIND_LABEL[data.kind] ?? data.kind.replace(/_/g, " ")) : "Evidence"}</div>
            <div className="mono mt-0.5 truncate text-base font-medium text-accent">{evidenceId}</div>
            {data && data.first_seen_tool_seq !== null ? (
              <div className="mt-0.5 text-xs text-dim">Fetched by the agent at tool call {data.first_seen_tool_seq}</div>
            ) : null}
          </div>
          <button ref={closeRef} type="button" onClick={onClose} className="btn btn-quiet shrink-0">
            Close <kbd className="mono rounded border border-edge px-1 text-[10px] text-dim">Esc</kbd>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isPending ? <Skeleton rows={5} label="Resolving citation" /> : null}

          {unverifiable ? (
            <div role="alert" className="rounded-lg border border-malicious/35 bg-malicious/10 p-4">
              <p className="text-sm font-semibold text-malicious">Unverifiable citation</p>
              <p className="mt-1 text-sm text-malicious/85">
                This run never fetched <span className="mono">{evidenceId}</span>. The verifier should have
                stripped the claim that cites it, so this points to a bug upstream, not a display problem.
              </p>
            </div>
          ) : error ? (
            <ErrorBox error={error} />
          ) : null}

          {data?.event ? (
            <dl>
              <Field label="Event id" value={data.event.event_id} />
              <Field label="Kind" value={data.event.kind} />
              <Field label="Timestamp" value={data.event.ts} />
              <Field label="Host" value={data.event.host} />
              <Field label="User" value={data.event.user} />
              <Field label="PID" value={data.event.pid} />
              <Field label="Parent PID" value={data.event.ppid} />
              <Field label="Image" value={data.event.image} />
              <Field label="Command line" value={data.event.command_line} />
              <Field label="Parent image" value={data.event.parent_image} />
              <Field label="Target image" value={data.event.target_image} />
              <Field label="Target path" value={data.event.target_path} />
              <Field label="Destination" value={data.event.dest_ip ?? data.event.dest_host} />
              <Field label="Port" value={data.event.dest_port} />
              <Field label="Query" value={data.event.query} />
              <Field label="Details" value={data.event.details} />
            </dl>
          ) : null}

          {data?.rule ? (
            <div className="space-y-4">
              <h3 className="text-base font-semibold">{data.rule.title}</h3>
              <p className="text-sm leading-relaxed text-dim">{data.rule.description}</p>
              <dl>
                <Field label="Slug" value={data.rule.slug} />
                <Field label="Level" value={data.rule.level} />
                <Field label="Tags" value={(data.rule.tags ?? []).join(", ")} />
              </dl>
              {(data.rule.falsepositives ?? []).length > 0 ? (
                <div>
                  <h4 className="label">Known false positives</h4>
                  <ul className="mt-1.5 list-inside list-disc space-y-1 text-sm text-dim">
                    {(data.rule.falsepositives ?? []).map((fp) => (
                      <li key={fp}>{fp}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}

          {data?.technique ? (
            <div className="space-y-4">
              <h3 className="text-base font-semibold">
                <span className="mono text-accent">{data.technique.technique_id}</span> {data.technique.name}
              </h3>
              <dl>
                <Field label="Tactics" value={data.technique.tactics.join(", ")} />
              </dl>
              <p className="text-sm leading-relaxed text-dim">{data.technique.description}</p>
            </div>
          ) : null}
        </div>
      </aside>
    </>
  );
}
