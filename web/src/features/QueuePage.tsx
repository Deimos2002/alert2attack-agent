import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { EmptyState, ErrorBox, Panel, SeverityBadge, Skeleton, VerdictBadge, utc } from "../components/ui";
import { api, type QueueFilters, type Severity, type Split, type Verdict } from "../lib/api";

function Stat({ label, value, tone = "text-text" }: { label: string; value: number | string; tone?: string }) {
  return (
    <div className="rounded-xl border border-edge bg-panel px-4 py-3">
      <dt className="label">{label}</dt>
      <dd className={`mono mt-1 text-2xl font-semibold tracking-tight ${tone}`}>{value}</dd>
    </div>
  );
}

/**
 * The alert queue.
 *
 * Filters live in the URL rather than in component state, so a filtered queue
 * is a link someone can send. That also removes most of what a client store
 * would otherwise hold.
 */
export function QueuePage() {
  const [params, setParams] = useSearchParams();

  const filters: QueueFilters = {
    split: (params.get("split") as Split | null) ?? "",
    severity: (params.get("severity") as Severity | null) ?? "",
    q: params.get("q") ?? "",
  };
  const filtered = Boolean(filters.split || filters.severity || filters.q);

  const { data, isPending, error } = useQuery({
    queryKey: ["scenarios", filters],
    queryFn: () => api.scenarios(filters),
  });

  // The latest finished run per case, so the queue shows what is already answered.
  const { data: jobs } = useQuery({
    queryKey: ["investigations"],
    queryFn: () => api.investigations(50),
  });
  const verdicts = new Map<string, Verdict>();
  for (const job of jobs ?? []) {
    if (job.status === "succeeded" && job.result && !verdicts.has(job.scenario_id)) {
      verdicts.set(job.scenario_id, job.result.case_file.verdict);
    }
  }

  function setFilter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  const rows = data ?? [];
  const urgent = rows.filter((r) => r.severity === "critical" || r.severity === "high").length;
  const investigated = rows.filter((r) => verdicts.has(r.scenario_id)).length;

  return (
    <div className="rise">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Alert queue</h1>
        <p className="mt-1 max-w-2xl text-sm text-dim">
          Each row is one alert on one host with a boxed window of telemetry. Open a case to run the
          investigation and check every claim against its evidence.
        </p>
      </header>

      <dl className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label={filtered ? "Matching cases" : "Cases"} value={data ? rows.length : "–"} />
        <Stat label="High or critical" value={data ? urgent : "–"} tone="text-malicious" />
        <Stat label="Investigated" value={data ? investigated : "–"} tone="text-benign" />
        <Stat label="Waiting" value={data ? rows.length - investigated : "–"} />
      </dl>

      <div className="mt-6 flex flex-wrap items-end gap-3">
        <label className="flex min-w-56 flex-1 flex-col gap-1 sm:max-w-sm">
          <span className="label">Search</span>
          <input
            type="search"
            value={filters.q}
            onChange={(e) => setFilter("q", e.target.value)}
            placeholder="Host, rule or case id"
            className="field"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">Severity</span>
          <select value={filters.severity} onChange={(e) => setFilter("severity", e.target.value)} className="field">
            <option value="">All</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="label">Dataset split</span>
          <select value={filters.split} onChange={(e) => setFilter("split", e.target.value)} className="field">
            <option value="">All</option>
            <option value="dev">Dev</option>
            <option value="test">Test (frozen)</option>
          </select>
        </label>
        {filtered ? (
          <button type="button" className="btn btn-quiet" onClick={() => setParams({}, { replace: true })}>
            Clear filters
          </button>
        ) : null}
      </div>

      <div className="mt-4">
        {error ? <ErrorBox error={error} /> : null}

        <Panel className="overflow-hidden">
          {isPending ? (
            <Skeleton rows={6} label="Loading queue" />
          ) : rows.length === 0 ? (
            <EmptyState
              title="No cases match those filters."
              hint="Loosen the search or clear the filters to see the whole queue."
              action={
                <button type="button" className="btn" onClick={() => setParams({}, { replace: true })}>
                  Clear filters
                </button>
              }
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[44rem] text-sm">
                <thead>
                  <tr className="border-b border-edge text-left">
                    <th className="label px-5 py-3">Severity</th>
                    <th className="label px-3 py-3">Alert</th>
                    <th className="label px-3 py-3">Host</th>
                    <th className="label px-3 py-3">Fired (UTC)</th>
                    <th className="label px-3 py-3">Verdict</th>
                    <th className="label px-5 py-3 text-right">Split</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const verdict = verdicts.get(row.scenario_id);
                    return (
                      <tr
                        key={row.scenario_id}
                        className="group relative border-b border-edge/60 transition-colors duration-150 last:border-0 hover:bg-raised/70"
                      >
                        <td className="px-5 py-3 align-top">
                          <SeverityBadge severity={row.severity} />
                        </td>
                        <td className="px-3 py-3">
                          {/* The link covers the whole row, so any click on it opens the case. */}
                          <Link
                            to={`/cases/${row.scenario_id}`}
                            className="font-medium text-text after:absolute after:inset-0 group-hover:text-accent"
                          >
                            {row.rule_title}
                          </Link>
                          <div className="mono mt-0.5 text-[11px] text-dim">{row.scenario_id}</div>
                        </td>
                        <td className="mono px-3 py-3 align-top text-xs text-dim">{row.host}</td>
                        <td className="mono px-3 py-3 align-top text-xs text-dim">{utc(row.fired_at)}</td>
                        <td className="px-3 py-3 align-top">
                          {verdict ? <VerdictBadge verdict={verdict} /> : <span className="text-xs text-dim/70">Not run</span>}
                        </td>
                        <td className="px-5 py-3 text-right align-top text-xs text-dim">{row.split}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
