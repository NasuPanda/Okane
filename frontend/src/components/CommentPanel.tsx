import { Check, ChevronDown, ChevronUp, Loader2, RefreshCw, ShieldAlert, ShieldCheck, Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useComment, useDecide } from "@/api/hooks";
import type { Comment, ExceptionRecord } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { cn } from "@/lib/utils";

function escape(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** The comment with every checked figure ticked green and every failed figure struck red. */
function Highlighted({ comment }: { comment: Comment }) {
  const figures = [
    ...comment.checked_figures.map((f) => ({ f, ok: true })),
    ...comment.failed_figures.map((f) => ({ f, ok: false })),
  ].sort((a, b) => b.f.length - a.f.length);
  if (!figures.length) return <>{comment.comment}</>;
  const pattern = new RegExp(`(${figures.map((x) => escape(x.f)).join("|")})`, "g");
  return (
    <>
      {comment.comment.split(pattern).map((part, i) => {
        const hit = figures.find((x) => x.f === part);
        if (!hit) return <span key={i}>{part}</span>;
        return (
          <span
            key={i}
            className={cn(
              "num mx-0.5 inline-flex items-center gap-0.5 rounded px-1 font-medium",
              hit.ok ? "bg-signal-soft text-signal-ink" : "bg-danger-soft text-destructive line-through",
            )}
          >
            {part}
            {hit.ok ? <Check className="size-3" strokeWidth={3} /> : <X className="size-3" strokeWidth={3} />}
          </span>
        );
      })}
    </>
  );
}

function VerifierBadge({ comment }: { comment: Comment }) {
  if (comment.verifier === "passed") {
    return (
      <Badge variant="signal">
        <ShieldCheck /> All {comment.checked_figures.length} numbers double-checked ✓
      </Badge>
    );
  }
  if (comment.verifier === "failed") {
    return (
      <Badge variant="danger">
        <ShieldAlert /> {comment.failed_figures.length} number(s) don't match our figures, please don't use this one
      </Badge>
    );
  }
  return <Badge variant="muted">Standard wording · numbers copied straight from the facts</Badge>;
}

/** Both AI drafts were turned down: say so, and keep the last one one click away. */
function RejectedDraft({ comment }: { comment: Comment }) {
  const [open, setOpen] = useState(false);
  if (!comment.rejected_draft) return null;
  const reasons = comment.rejected_reasons ?? [];
  return (
    <div className="space-y-2 border-t pt-3 text-[13px] text-muted-foreground">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span>The assistant's draft had something we couldn't confirm, so standard wording is shown.</span>
        <Button size="sm" variant="ghost" onClick={() => setOpen((v) => !v)}>
          {open ? <ChevronUp /> : <ChevronDown />}
          {open ? "Hide the assistant's draft" : "Show the assistant's draft"}
        </Button>
      </div>
      {open && (
        <div className="space-y-2 rounded-lg border border-dashed p-3">
          <p className="leading-relaxed line-through decoration-destructive/40">{comment.rejected_draft}</p>
          {reasons.length > 0 && (
            <ul className="list-inside list-disc text-destructive">
              {reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function CommentPanel({ record }: { record: ExceptionRecord }) {
  const draft = useComment(record.id);
  const decide = useDecide(record.id);
  const [edited, setEdited] = useState(record.edited_comment ?? "");
  const comment = draft.data;

  useEffect(() => setEdited(record.edited_comment ?? ""), [record.id, record.edited_comment]);
  // Show the stored draft straight away when one exists (served from the cache, no new call).
  const { mutate } = draft;
  const hasStored = !!record.ai_comment;
  useEffect(() => {
    if (hasStored) mutate(false);
  }, [record.id, hasStored, mutate]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="eyebrow flex items-center gap-1.5">
          <Sparkles className="size-3.5 text-sentinel" /> Draft note
        </span>
        <Button size="sm" variant="outline" onClick={() => draft.mutate(!!comment)} disabled={draft.isPending}>
          {draft.isPending ? <Loader2 className="animate-spin" /> : comment ? <RefreshCw /> : <Sparkles />}
          {comment ? "Try again" : "Write a draft for me"}
        </Button>
      </div>
      {comment ? (
        <div className="rise space-y-3 rounded-xl border-l-4 border-sentinel bg-secondary p-4">
          <p className="text-[15px] leading-relaxed">
            <Highlighted comment={comment} />
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <VerifierBadge comment={comment} />
            <span className="text-[11px] text-muted-foreground">
              {comment.source === "model"
                ? "Drafted by the local AI assistant"
                : comment.rejected_draft
                  ? "Standard wording (the assistant's draft was not used)"
                  : "No AI was used for this one"}
              {comment.cached && " · cached"}
            </span>
          </div>
          <RejectedDraft key={`${comment.exception_id}:${comment.rejected_draft ?? ""}`} comment={comment} />
        </div>
      ) : (
        <p className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
          Want a head start? The assistant drafts a short note for you. It only picks the words: every number it
          writes is checked against Okane's own figures, and it never decides an amount, a date, a priority or a class.
        </p>
      )}
      <div className="space-y-2">
        <Textarea
          value={edited}
          onChange={(e) => setEdited(e.target.value)}
          placeholder="Your own note for the reconciliation file (kept separate from the draft)"
          className="min-h-16"
        />
        <div className="flex justify-end gap-2">
          {comment && (
            <Button size="sm" variant="ghost" onClick={() => setEdited(comment.comment)}>
              Copy the draft
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            disabled={decide.isPending || edited === (record.edited_comment ?? "")}
            onClick={() => decide.mutate({ edited_comment: edited })}
          >
            Save note
          </Button>
        </div>
      </div>
    </div>
  );
}
