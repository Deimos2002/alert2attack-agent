import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorBox, Panel, SectionTitle, VERDICT_LABEL, utc } from "../components/ui";
import { api, type Verdict } from "../lib/api";

const VERDICTS: Verdict[] = ["malicious", "suspicious", "likely_benign", "not_enough_evidence"];

/**
 * Records whether an analyst agrees with a case file.
 *
 * It never edits the case file. A review is an observation about what the
 * agent said on that run, and the run's record stays as it was — the API
 * enforces this, and the UI should not suggest otherwise.
 */
export function ReviewForm({ jobId, scenarioId }: { jobId: string; scenarioId: string }) {
  const queryClient = useQueryClient();
  const [agrees, setAgrees] = useState<boolean | null>(null);
  const [verdict, setVerdict] = useState<Verdict>("likely_benign");
  const [note, setNote] = useState("");

  const { data: existing } = useQuery({
    queryKey: ["reviews", scenarioId],
    queryFn: () => api.reviews(scenarioId),
  });

  const submit = useMutation({
    mutationFn: () =>
      api.addReview(jobId, {
        agrees: agrees === true,
        corrected_verdict: agrees === false ? verdict : null,
        note,
      }),
    onSuccess: () => {
      setAgrees(null);
      setNote("");
      void queryClient.invalidateQueries({ queryKey: ["reviews", scenarioId] });
    },
  });

  return (
    <Panel>
      <SectionTitle>Your review</SectionTitle>

      <div className="px-5 pb-5">
        <p className="text-sm text-dim">Do you agree with the verdict?</p>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <button
            type="button"
            aria-pressed={agrees === true}
            onClick={() => setAgrees(true)}
            className={`btn ${agrees === true ? "border-benign/60 bg-benign/15 text-benign hover:border-benign/60 hover:bg-benign/15" : ""}`}
          >
            Agree
          </button>
          <button
            type="button"
            aria-pressed={agrees === false}
            onClick={() => setAgrees(false)}
            className={`btn ${agrees === false ? "border-malicious/60 bg-malicious/15 text-malicious hover:border-malicious/60 hover:bg-malicious/15" : ""}`}
          >
            Disagree
          </button>
        </div>

        {agrees === false ? (
          <label className="mt-3 flex flex-col gap-1">
            <span className="label">It should have been</span>
            <select value={verdict} onChange={(e) => setVerdict(e.target.value as Verdict)} className="field">
              {VERDICTS.map((v) => (
                <option key={v} value={v}>
                  {VERDICT_LABEL[v]}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {agrees !== null ? (
          <>
            <label className="mt-3 flex flex-col gap-1">
              <span className="label">Why (optional)</span>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="The reason is what makes this useful later"
                rows={3}
                className="field py-2"
              />
            </label>
            <button
              type="button"
              disabled={submit.isPending}
              onClick={() => submit.mutate()}
              className="btn btn-primary mt-3 w-full"
            >
              {submit.isPending ? "Saving…" : "Save review"}
            </button>
          </>
        ) : null}

        {submit.error ? (
          <div className="mt-3">
            <ErrorBox error={submit.error} />
          </div>
        ) : null}

        <p className="mt-4 text-xs leading-relaxed text-dim">
          Reviews are kept alongside the run and never change the case file. A disagreement that names a
          verdict becomes a candidate test case for a person to curate.
        </p>
      </div>

      {existing && existing.length > 0 ? (
        <ul className="border-t border-edge px-5 py-2">
          {existing.map((review) => (
            <li key={review.id} className="border-b border-edge/40 py-2 text-xs last:border-0">
              <span className={review.agrees ? "font-medium text-benign" : "font-medium text-malicious"}>
                {review.agrees
                  ? "Agreed"
                  : `Disagreed: ${review.corrected_verdict ? VERDICT_LABEL[review.corrected_verdict] : "no verdict given"}`}
              </span>
              <div className="mt-0.5 text-dim">
                {review.reviewer} · <span className="mono">{utc(review.created_at)}</span>
              </div>
              {review.note ? <p className="mt-1 leading-relaxed text-text/90">{review.note}</p> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </Panel>
  );
}
