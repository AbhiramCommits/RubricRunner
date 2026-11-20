import Link from "next/link";
import { notFound } from "next/navigation";

import { formatDate, formatPoints } from "@/components/StatusBadge";
import { apiFetch } from "@/lib/api";
import type { AuditTrail, Submission } from "@/lib/types";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ id: string; submissionId: string }>;
};

export default async function HistoryPage({ params }: PageProps) {
  const { id, submissionId } = await params;
  const assignmentId = Number(id);
  const numericSubmissionId = Number(submissionId);
  if (Number.isNaN(assignmentId) || Number.isNaN(numericSubmissionId)) notFound();

  let submission: Submission;
  try {
    submission = await apiFetch<Submission>(`/submissions/${numericSubmissionId}`);
  } catch {
    notFound();
  }

  let audit: AuditTrail | null = null;
  if (submission.published_version_id !== null) {
    try {
      audit = await apiFetch<AuditTrail>(`/submissions/${numericSubmissionId}/audit-trail`);
    } catch {
      audit = null;
    }
  }

  const versions = [...submission.versions].reverse();

  return (
    <div className="space-y-6">
      <div>
        <Link
          href={`/assignments/${assignmentId}/submissions/${submission.id}`}
          className="text-xs text-indigo-600 hover:underline"
        >
          ← Back to review
        </Link>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">
          Version history · {submission.student_name}
        </h1>
        <p className="text-sm text-slate-500">
          {submission.assignment_title} · every AI score and teacher edit is append-only.
        </p>
      </div>

      <ol className="relative space-y-3 border-l-2 border-slate-200 pl-6">
        {versions.map((version) => (
          <li key={version.id} className="relative">
            <span
              className={`absolute -left-[31px] top-3 h-3 w-3 rounded-full border-2 border-white ${
                version.source === "ai" ? "bg-sky-500" : "bg-violet-500"
              }`}
            />
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-mono text-xs text-slate-400">#{version.id}</span>
                <span
                  className={`rounded px-2 py-0.5 text-xs font-semibold ${
                    version.source === "ai"
                      ? "bg-sky-100 text-sky-700"
                      : "bg-violet-100 text-violet-700"
                  }`}
                >
                  {version.source === "ai" ? "AI" : "Teacher"}
                </span>
                <span className="text-sm font-semibold text-slate-900">
                  {formatPoints(version.total_points)} / {submission.max_points}
                </span>
                {version.needs_review ? (
                  <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                    needs review
                  </span>
                ) : null}
                {submission.published_version_id === version.id ? (
                  <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700">
                    published
                  </span>
                ) : null}
                <span className="ml-auto text-xs text-slate-400">
                  {formatDate(version.created_at)}
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                prompt <span className="font-mono">{version.prompt_version || "—"}</span> · author{" "}
                <span className="font-mono">{version.created_by}</span>
                {version.parent_version_id !== null
                  ? ` · parent #${version.parent_version_id}`
                  : " · root version"}
                {version.grading_run_id !== null
                  ? ` · run #${version.grading_run_id}`
                  : ""}
              </p>
              <ul className="mt-3 grid gap-1 text-xs text-slate-600 sm:grid-cols-2">
                {version.criteria.map((score) => (
                  <li key={score.criterion_id} className="flex justify-between gap-2">
                    <span>{score.criterion_name}</span>
                    <span className="tabular-nums font-medium text-slate-800">
                      {formatPoints(score.points)}
                      {score.confidence !== null ? (
                        <span className="ml-1 font-normal text-slate-400">
                          (conf {score.confidence.toFixed(2)})
                        </span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 rounded bg-slate-50 px-3 py-2 text-xs text-slate-600">
                {version.summary_comment}
              </p>
              {version.raw_model_output !== null ? (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs font-medium text-indigo-600">
                    Raw model output
                  </summary>
                  <pre className="mt-2 max-h-80 overflow-auto rounded bg-slate-900 p-3 text-[11px] leading-5 text-slate-100">
                    {JSON.stringify(version.raw_model_output, null, 2)}
                  </pre>
                </details>
              ) : null}
            </div>
          </li>
        ))}
      </ol>

      {audit !== null ? (
        <section className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-emerald-800">
            Audit trail of published grade
          </h2>
          <p className="mt-1 text-xs text-emerald-700">
            Published {formatDate(audit.published.published_at)} by {audit.published.published_by} ·
            version #{audit.published.feedback_version_id} · {audit.chain.length}-version lineage
          </p>
          <ol className="mt-3 space-y-2">
            {audit.chain.map((version) => (
              <li
                key={version.id}
                className="flex flex-wrap items-center gap-2 rounded bg-white/70 px-3 py-2 text-xs"
              >
                <span className="font-mono">#{version.id}</span>
                <span className="font-semibold">
                  {version.source === "ai" ? "AI" : "Teacher"}
                </span>
                <span className="font-mono text-slate-500">{version.prompt_version || "—"}</span>
                <span className="tabular-nums">{formatPoints(version.total_points)} pts</span>
                {version.raw_model_output !== null ? (
                  <span className="rounded bg-sky-100 px-1.5 py-0.5 text-sky-700">
                    raw model output preserved
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}
    </div>
  );
}
