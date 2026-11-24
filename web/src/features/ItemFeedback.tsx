import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ErrorBox } from "../components/ui";
import { api, type ItemFeedback } from "../lib/api";

/**
 * A person's decision on one item of a case file.
 *
 * Actions are approved or rejected; timeline entries and techniques can be
 * disputed. The case file never changes: each decision is stored beside it,
 * append-only, and the latest one per item is what shows here.
 */
export function useItemFeedback(jobId: string) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["feedback", jobId], queryFn: () => api.feedback(jobId) });
  // The API lists newest first, so the first row seen per item is the current decision.
  const latest = new Map<string, ItemFeedback>();
  for (const row of data ?? []) if (!latest.has(row.target)) latest.set(row.target, row);

  const submit = useMutation({
    mutationFn: (body: { target: string; decision: ItemFeedback["decision"]; reason: string }) =>
      api.addFeedback(jobId, body),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["feedback", jobId] }),
  });
  return { latest, submit };
}

type Feedback = ReturnType<typeof useItemFeedback>;

function ReasonForm({
  label,
  placeholder,
  onSubmit,
  onCancel,
}: {
  label: string;
  placeholder: string;
  onSubmit: (reason: string) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState("");
  return (
    <form
      className="mt-2 flex flex-col gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (reason.trim()) onSubmit(reason.trim());
      }}
    >
      <textarea
        aria-label={label}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        maxLength={1000}
        rows={2}
        placeholder={placeholder}
        className="field min-h-0 py-2"
        autoFocus
      />
      <div className="flex gap-2">
        <button type="submit" className="btn" disabled={!reason.trim()}>
          {label}
        </button>
        <button type="button" className="btn btn-quiet" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** Approve / Reject for one recommended action. Until a person decides, it is pending. */
export function ActionDecision({ target, feedback }: { target: string; feedback: Feedback }) {
  const [rejecting, setRejecting] = useState(false);
  const current = feedback.latest.get(target);
  const send = (decision: "approve" | "reject", reason = "") =>
    feedback.submit.mutate({ target, decision, reason }, { onSuccess: () => setRejecting(false) });

  return (
    <div className="mt-3 border-t border-edge/60 pt-3">
      <p className="text-xs">
        {current?.decision === "approve" ? (
          <span className="text-benign">Approved by {current.reviewer}</span>
        ) : current?.decision === "reject" ? (
          <span className="text-suspicious">
            Rejected by {current.reviewer}: {current.reason}
          </span>
        ) : (
          <span className="text-dim">Pending: needs a person's decision</span>
        )}
      </p>
      {rejecting ? (
        <ReasonForm
          label="Reject"
          placeholder="Why not? e.g. this host is the backup server"
          onSubmit={(reason) => send("reject", reason)}
          onCancel={() => setRejecting(false)}
        />
      ) : (
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            className="btn"
            disabled={feedback.submit.isPending || current?.decision === "approve"}
            onClick={() => send("approve")}
          >
            Approve
          </button>
          <button
            type="button"
            className="btn"
            disabled={feedback.submit.isPending}
            onClick={() => setRejecting(true)}
          >
            Reject
          </button>
        </div>
      )}
      {feedback.submit.error ? <ErrorBox error={feedback.submit.error} /> : null}
    </div>
  );
}

/** A quiet "Dispute" control on a claim, and the dispute once there is one. */
export function ClaimDispute({ target, feedback }: { target: string; feedback: Feedback }) {
  const [open, setOpen] = useState(false);
  const current = feedback.latest.get(target);

  if (open) {
    return (
      <ReasonForm
        label="Dispute"
        placeholder="What is wrong with this? e.g. pid 1244 is VBoxService, not the attacker"
        onSubmit={(reason) =>
          feedback.submit.mutate({ target, decision: "dispute", reason }, { onSuccess: () => setOpen(false) })
        }
        onCancel={() => setOpen(false)}
      />
    );
  }
  return (
    <div className="mt-1.5 flex flex-wrap items-baseline gap-x-3 text-xs">
      {current ? (
        <span className="text-suspicious">
          Disputed by {current.reviewer}: {current.reason}
        </span>
      ) : null}
      <button type="button" className="text-dim underline-offset-2 hover:text-text hover:underline" onClick={() => setOpen(true)}>
        {current ? "Change" : "Dispute"}
      </button>
    </div>
  );
}
