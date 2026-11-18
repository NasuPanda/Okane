import { Check, Loader2, RefreshCw, ShieldAlert, ShieldCheck, Sparkles, X } from "lucide-react";
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
        <ShieldCheck /> All {comment.checked_figures.length} figures match the computed facts
      </Badge>
    );
  }
  if (comment.verifier === "failed") {
    return (
      <Badge variant="danger">
        <ShieldAlert /> {comment.failed_figures.length} figure(s) not in the facts: do not use
      </Badge>
    );
  }
  return <Badge variant="muted">Template text · figures copied from the facts, check not run</Badge>;
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
      <div className="flex items-center justify-between">
        <span className="eyebrow flex items-center gap-1.5">
          <Sparkles className="size-3.5" /> Draft comment
        </span>
        <Button size="sm" variant="outline" onClick={() => draft.mutate(!!comment)} disabled={draft.isPending}>
          {draft.isPending ? <Loader2 className="animate-spin" /> : comment ? <RefreshCw /> : <Sparkles />}
          {comment ? "Redraft" : "Draft comment"}
        </Button>
      </div>
      {comment ? (
        <div className="space-y-3 rounded-xl bg-secondary p-4">
          <p className="text-[15px] leading-relaxed">
            <Highlighted comment={comment} />
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <VerifierBadge comment={comment} />
            <span className="text-[11px] text-muted-foreground">
              {comment.source === "model" ? "Written by the local language model" : "No language model was used"}
              {comment.cached && " · cached"}
            </span>
          </div>
        </div>
      ) : (
        <p className="rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
          The model only words the comment. Every figure it writes is checked against the facts below; it never
          sets an amount, a date, a rank or a class.
        </p>
      )}
      <div className="space-y-2">
        <Textarea
          value={edited}
          onChange={(e) => setEdited(e.target.value)}
          placeholder="Your comment for the reconciliation file (kept separate from the draft)"
          className="min-h-16"
        />
        <div className="flex justify-end gap-2">
          {comment && (
            <Button size="sm" variant="ghost" onClick={() => setEdited(comment.comment)}>
              Use draft
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            disabled={decide.isPending || edited === (record.edited_comment ?? "")}
            onClick={() => decide.mutate({ edited_comment: edited })}
          >
            Save comment
          </Button>
        </div>
      </div>
    </div>
  );
}
