import type { RosterStatus } from "@/lib/types";

const STYLES: Record<RosterStatus, string> = {
  ungraded: "bg-slate-100 text-slate-600 ring-slate-200",
  ai_graded: "bg-sky-50 text-sky-700 ring-sky-200",
  needs_review: "bg-amber-50 text-amber-800 ring-amber-200",
  teacher_edited: "bg-violet-50 text-violet-700 ring-violet-200",
  published: "bg-emerald-50 text-emerald-700 ring-emerald-200",
};

const LABELS: Record<RosterStatus, string> = {
  ungraded: "Ungraded",
  ai_graded: "AI graded",
  needs_review: "Needs review",
  teacher_edited: "Teacher edited",
  published: "Published",
};

export function StatusBadge({ status }: { status: RosterStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${STYLES[status]}`}
    >
      {LABELS[status]}
    </span>
  );
}

const RUN_STYLES: Record<string, string> = {
  queued: "bg-slate-100 text-slate-600",
  running: "bg-sky-100 text-sky-700",
  succeeded: "bg-emerald-100 text-emerald-700",
  partial: "bg-amber-100 text-amber-800",
  failed: "bg-red-100 text-red-700",
};

export function RunBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold ${RUN_STYLES[status] ?? "bg-slate-100 text-slate-600"}`}
    >
      {status}
    </span>
  );
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatPoints(value: number | null): string {
  if (value === null) return "—";
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}
