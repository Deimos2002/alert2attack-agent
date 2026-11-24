import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  EmptyState,
  ErrorBox,
  EvidenceChips,
  Panel,
  SectionTitle,
  SeverityBadge,
  Skeleton,
  VERDICT_LABEL,
  VERDICT_TONE,
  utc,
} from "../components/ui";
import { api, type AgentModel, type CaseFile, type InvestigationJob } from "../lib/api";
import { useInvestigationStream } from "../lib/useInvestigationStream";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { ReviewForm } from "./ReviewForm";
import { TraceView } from "./TraceView";

type OpenEvidence = (id: string) => void;

// Which model the Run button asks for. A build sets VITE_AGENT_MODEL; the default
// needs no model at all.
const AGENT_MODEL = (import.meta.env.VITE_AGENT_MODEL ?? "replay") as AgentModel;

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="mono mt-0.5 text-sm text-text">{children}</dd>
    </div>
  );
}

function AlertHeader({ scenarioId }: { scenarioId: string }) {
  const { data, isPending, error } = useQuery({
    queryKey: ["scenario", scenarioId],
    queryFn: () => api.scenario(scenarioId),
  });

  if (isPending) return <Skeleton rows={3} label="Loading alert" />;
  if (error) return <ErrorBox error={error} />;
  if (!data) return null;

  return (
    <header>
      <SeverityBadge severity={data.severity} />
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">{data.rule_title}</h1>
      <p className="mono mt-1 text-xs text-dim">{scenarioId}</p>
      <dl className="mt-5 grid grid-cols-2 gap-x-8 gap-y-4 border-y border-edge py-4 sm:grid-cols-4">
        <Fact label="Host">{data.host}</Fact>
        <Fact label="Fired (UTC)">{utc(data.fired_at)}</Fact>
        <Fact label="Telemetry window">
          {data.window_start.slice(11, 19)} to {data.window_end.slice(11, 19)}
        </Fact>
        <Fact label="Events in window">{data.event_count}</Fact>
      </dl>
    </header>
  );
}

const CONFIDENCE_LEVEL = { low: 1, medium: 2, high: 3 } as const;

function Confidence({ level }: { level: CaseFile["confidence"] }) {
  return (
    <span className="inline-flex items-center gap-2 text-xs text-dim">
      <span className="flex gap-0.5" aria-hidden>
        {[1, 2, 3].map((n) => (
          <span key={n} className={`h-3 w-1 rounded-sm ${n <= CONFIDENCE_LEVEL[level] ? "bg-text" : "bg-edge"}`} />
        ))}
      </span>
      {level} confidence
    </span>
  );
}

function sentence(action: string): string {
  const words = action.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function CaseFileView({
  caseFile,
  job,
  onOpenEvidence,
}: {
  caseFile: CaseFile;
  job: InvestigationJob;
  onOpenEvidence: OpenEvidence;
}) {
  const verification = job.result?.verification;
  const tone = VERDICT_TONE[caseFile.verdict];
  const citations = new Set([
    ...caseFile.timeline.flatMap((t) => t.evidence),
    ...caseFile.techniques.flatMap((t) => t.evidence),
    ...caseFile.next_actions.flatMap((a) => a.rationale.evidence),
  ]).size;

  return (
    <div className="rise space-y-4">
      <Panel className="relative overflow-hidden">
        <span aria-hidden className={`absolute inset-y-0 left-0 w-1 ${tone.bar}`} />
        <div className="px-6 py-5">
          <div className="label">Verdict</div>
          <div className="mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <p className={`text-3xl font-semibold tracking-tight ${tone.text}`}>{VERDICT_LABEL[caseFile.verdict]}</p>
            <Confidence level={caseFile.confidence} />
          </div>
          <p className="mt-3 max-w-[68ch] text-[15px] leading-relaxed text-text/90">{caseFile.summary}</p>
          <p className="mt-4 text-xs text-dim">
            {citations} citation{citations === 1 ? "" : "s"} · {caseFile.techniques.length} technique
            {caseFile.techniques.length === 1 ? "" : "s"} · model <span className="mono">{job.model}</span> · run {job.created_at.slice(0, 10)} ·{" "}
            {verification ? (
              verification.status === "passed" ? (
                <span className="text-benign">every citation verified</span>
              ) : (
                <span className="text-suspicious">verification {verification.status}</span>
              )
            ) : (
              "not verified"
            )}
          </p>
        </div>
        {verification && verification.status !== "passed" ? (
          <div className="border-t border-suspicious/30 bg-suspicious/10 px-6 py-3 text-sm text-suspicious">
            {verification.stripped_claims} claim(s) could not be backed by fetched evidence after{" "}
            {verification.repairs_used} repair turn(s). They were removed from this case file, not shipped.
          </div>
        ) : null}
      </Panel>

      {caseFile.next_actions.length > 0 ? (
        <Panel>
          <SectionTitle aside="Nothing here is executed">Recommended actions</SectionTitle>
          <ul className="grid gap-3 px-5 pb-5 sm:grid-cols-2">
            {caseFile.next_actions.map((a, i) => (
              <li key={i} className="rounded-lg border border-edge bg-raised/50 p-4">
                <div className="text-sm font-semibold">{sentence(a.action)}</div>
                <p className="mt-1 text-sm leading-relaxed text-dim">{a.rationale.text}</p>
                <EvidenceChips ids={a.rationale.evidence} onOpen={onOpenEvidence} />
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {caseFile.timeline.length > 0 ? (
        <Panel>
          <SectionTitle aside="Click a citation to open the record">What happened</SectionTitle>
          <ol className="px-5 pb-5">
            {caseFile.timeline.map((entry, i) => (
              <li key={i} className="relative flex gap-4 pb-5 last:pb-0">
                {i === caseFile.timeline.length - 1 ? null : (
                  <span aria-hidden className="absolute top-4 left-[5px] h-full w-px bg-edge" />
                )}
                <span aria-hidden className="relative mt-1.5 size-[11px] shrink-0 rounded-full border-2 border-accent bg-panel" />
                <div className="min-w-0">
                  {entry.ts.startsWith("1970") ? null : <time className="mono text-xs text-dim">{utc(entry.ts)}</time>}
                  <p className="mt-0.5 text-sm leading-relaxed">{entry.text}</p>
                  <EvidenceChips ids={entry.evidence} onOpen={onOpenEvidence} />
                </div>
              </li>
            ))}
          </ol>
        </Panel>
      ) : null}

      {caseFile.techniques.length > 0 ? (
        <Panel>
          <SectionTitle>ATT&amp;CK techniques</SectionTitle>
          <ul className="px-5 pb-4">
            {caseFile.techniques.map((t) => (
              <li key={t.technique_id} className="border-b border-edge/50 py-3 last:border-0">
                <div className="flex flex-wrap items-baseline gap-x-3">
                  <span className="mono text-sm font-medium text-text">{t.technique_id}</span>
                  {t.note ? <span className="text-sm text-dim">{t.note}</span> : null}
                </div>
                <EvidenceChips ids={t.evidence} onOpen={onOpenEvidence} />
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {caseFile.scope.root_process || caseFile.scope.involved_pids.length > 0 || caseFile.scope.persistence.length > 0 ? (
        <Panel>
          <SectionTitle aside={caseFile.scope.beyond_process ? "Reaches beyond one process" : undefined}>
            Scope
          </SectionTitle>
          <div className="space-y-4 px-5 pb-5 text-sm">
            {caseFile.scope.root_process ? (
              <div>
                <div className="label">Root process</div>
                <p className="mt-1 leading-relaxed">{caseFile.scope.root_process.text}</p>
                <EvidenceChips ids={caseFile.scope.root_process.evidence} onOpen={onOpenEvidence} />
              </div>
            ) : null}
            {caseFile.scope.involved_pids.length > 0 ? (
              <div>
                <div className="label">Processes involved</div>
                <p className="mono mt-1 text-xs leading-relaxed text-dim">{caseFile.scope.involved_pids.join("  ")}</p>
              </div>
            ) : null}
            {caseFile.scope.persistence.map((claim, i) => (
              <div key={i}>
                <div className="label">Persistence</div>
                <p className="mt-1 leading-relaxed">{claim.text}</p>
                <EvidenceChips ids={claim.evidence} onOpen={onOpenEvidence} />
              </div>
            ))}
          </div>
        </Panel>
      ) : null}

      {caseFile.open_questions.length > 0 ? (
        <Panel>
          <SectionTitle>Open questions</SectionTitle>
          <ul className="list-outside list-disc space-y-1.5 px-5 pb-5 pl-9 text-sm leading-relaxed text-dim">
            {caseFile.open_questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        </Panel>
      ) : null}
    </div>
  );
}

function TelemetryTable({ scenarioId }: { scenarioId: string }) {
  const [draft, setDraft] = useState("");
  const [q, setQ] = useState("");
  const { data, isPending, error } = useQuery({
    queryKey: ["events", scenarioId, q],
    queryFn: () => api.events(scenarioId, { limit: 100, q: q || undefined }),
  });

  return (
    <Panel className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 pt-4 pb-3">
        <div>
          <h2 className="text-sm font-semibold">Raw telemetry</h2>
          <p className="text-xs text-dim">
            {data ? `${data.events.length}${data.next_cursor ? "+" : ""} events` : "Loading"} · what the agent could
            read, whether or not it did
          </p>
        </div>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setQ(draft.trim());
          }}
        >
          <input
            type="search"
            aria-label="Filter telemetry"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Filter, e.g. powershell"
            className="field w-48"
          />
          <button type="submit" className="btn">
            Filter
          </button>
        </form>
      </div>

      {error ? (
        <div className="px-5 pb-4">
          <ErrorBox error={error} />
        </div>
      ) : isPending ? (
        <Skeleton rows={4} label="Loading telemetry" />
      ) : data.events.length === 0 ? (
        <EmptyState title="No events match that filter." />
      ) : (
        <div className="max-h-[26rem] overflow-auto border-t border-edge">
          <table className="w-full min-w-[40rem] text-xs">
            <thead className="sticky top-0 bg-panel">
              <tr className="border-b border-edge text-left">
                <th className="label px-5 py-2">Id</th>
                <th className="label px-3 py-2">Time</th>
                <th className="label px-3 py-2">Kind</th>
                <th className="label px-3 py-2">PID</th>
                <th className="label px-3 py-2">Image or detail</th>
              </tr>
            </thead>
            <tbody>
              {data.events.map((e) => (
                <tr key={e.event_id} className="border-b border-edge/40 transition-colors last:border-0 hover:bg-raised/60">
                  <td className="mono px-5 py-1.5 text-dim">{e.event_id}</td>
                  <td className="mono px-3 py-1.5 text-dim">{e.ts.slice(11, 23)}</td>
                  <td className="px-3 py-1.5 text-dim">{e.kind.replace(/_/g, " ")}</td>
                  <td className="mono px-3 py-1.5 text-dim">{e.pid ?? "–"}</td>
                  <td className="mono max-w-md truncate px-3 py-1.5" title={e.command_line ?? e.image ?? ""}>
                    {e.command_line ?? e.image ?? e.target_path ?? e.details ?? "–"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data?.next_cursor ? (
        <p className="border-t border-edge px-5 py-2.5 text-xs text-dim">
          Showing the first 100 events. Filter to narrow the window.
        </p>
      ) : null}
    </Panel>
  );
}

export function CasePage() {
  const { scenarioId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();
  const openEvidence = params.get("ev");

  // The job this page is streaming, if the user started one on this visit.
  const [liveJobId, setLiveJobId] = useState<string | null>(null);

  const { data: jobs } = useQuery({
    queryKey: ["investigations"],
    queryFn: () => api.investigations(50),
  });

  const trace = useInvestigationStream(liveJobId, () => {
    // `done` means "refetch over REST" — the stream never carries a case file.
    void queryClient.invalidateQueries({ queryKey: ["investigations"] });
  });

  const start = useMutation({
    mutationFn: () => api.startInvestigation(scenarioId, AGENT_MODEL),
    onSuccess: (job) => setLiveJobId(job.id),
  });

  // Prefer the run happening now; otherwise the latest finished one.
  const finished = jobs?.find((j) => j.scenario_id === scenarioId && j.status === "succeeded");
  const liveJob = jobs?.find((j) => j.id === liveJobId);
  const job = liveJob?.status === "succeeded" ? liveJob : finished;

  function setEvidence(id: string | null) {
    const next = new URLSearchParams(params);
    if (id) next.set("ev", id);
    else next.delete("ev");
    setParams(next, { replace: true });
  }

  const running = trace.status === "connecting" || trace.status === "streaming";

  return (
    <div>
      <nav aria-label="Breadcrumb" className="text-sm">
        <Link to="/" className="text-dim transition-colors hover:text-text">
          Alert queue
        </Link>
        <span aria-hidden className="mx-2 text-dim/50">
          /
        </span>
        <span className="text-text">Case</span>
      </nav>

      <div className="mt-4">
        <AlertHeader scenarioId={scenarioId} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_21rem]">
        <div className="min-w-0 space-y-4">
          {start.error ? <ErrorBox error={start.error} /> : null}

          {job?.result ? (
            <CaseFileView caseFile={job.result.case_file} job={job} onOpenEvidence={(id) => setEvidence(id)} />
          ) : running ? (
            <Panel>
              <Skeleton rows={4} label="Investigation running" />
            </Panel>
          ) : (
            <Panel>
              <EmptyState
                title="This alert has not been investigated yet."
                hint="Run the investigation to get a verdict, a timeline and recommended actions, each tied to evidence you can open."
                action={
                  <button type="button" className="btn btn-primary" disabled={start.isPending} onClick={() => start.mutate()}>
                    Run investigation
                  </button>
                }
              />
            </Panel>
          )}

          <TelemetryTable scenarioId={scenarioId} />
        </div>

        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <Panel className="p-5">
            <button
              type="button"
              disabled={running || start.isPending}
              onClick={() => start.mutate()}
              className="btn w-full"
            >
              {running ? "Investigating…" : job?.result ? "Run again" : "Run investigation"}
            </button>
            <p className="mt-3 text-xs leading-relaxed text-dim">
              {AGENT_MODEL === "replay"
                ? "Replay mode: a scripted stand-in for the model, so it runs without a GPU."
                : "Runs on a live model, up to a daily limit. Past the limit, a scripted replay stands in and the case file says so."}{" "}
              The tools, evidence ledger, citation verifier and safety rules around it are the real ones.
            </p>
          </Panel>

          {liveJobId ? <TraceView trace={trace} /> : null}

          {job?.result ? <ReviewForm jobId={job.id} scenarioId={scenarioId} /> : null}
        </aside>
      </div>

      {openEvidence && job ? (
        <EvidenceDrawer jobId={job.id} evidenceId={openEvidence} onClose={() => setEvidence(null)} />
      ) : null}
    </div>
  );
}
