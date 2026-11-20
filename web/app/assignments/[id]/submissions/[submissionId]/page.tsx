import Link from "next/link";
import { notFound } from "next/navigation";

import { publishVersion, saveTeacherVersion } from "@/app/actions";
import { formatDate, formatPoints } from "@/components/StatusBadge";
import { apiFetch } from "@/lib/api";
import type { CriterionScore, FeedbackVersion, RubricCriterion, Submission } from "@/lib/types";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ id: string; submissionId: string }>;
  searchParams: Promise<{ version?: string; saved?: string; error?: string }>;
};

function reasonsFor(version: FeedbackVersion): string[] {
  const raw = version.raw_model_output;
  if (raw === null) return [];
  const reasons = raw.needs_review_reasons;
  if (!Array.isArray(reasons)) return [];
  return reasons.filter((reason): reason is string => typeof reason === "string");
}

function scoreFor(version: FeedbackVersion | null, criterionId: number): CriterionScore | null {
  if (version === null) return null;
  return version.criteria.find((score) => score.criterion_id === criterionId) ?? null;
}

export default async function ReviewPage({ params, searchParams }: PageProps) {
  const { id, submissionId } = await params;
  const query = await searchParams;
  const assignmentId = Number(id);
  const numericSubmissionId = Number(submissionId);
  if (Number.isNaN(assignmentId) || Number.isNaN(numericSubmissionId)) notFound();

  let submission: Submission;
  try {
    submission = await apiFetch<Submission>(`/submissions/${numericSubmissionId}`);
  } catch {
    notFound();
  }

  const versions = submission.versions;
  const selected =
    (query.version ? versions.find((version) => String(version.id) === query.version) : undefined) ??
    versions[versions.length - 1] ??
    null;
  if (selected === null) {
    return (
      <div className="space-y-4">
        <Link href={`/assignments/${assignmentId}`} className="text-xs text-indigo-600 hover:underline">
          ← Back to roster
        </Link>
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-8">
          <h1 className="text-lg font-semibold text-slate-900">{submission.student_name}</h1>
          <p className="mt-2 text-sm text-slate-600">
            This submission has not been graded yet. Start a class grading run from the roster.
          </p>
        </div>
      </div>
    );
  }

  const parent =
    selected.parent_version_id !== null
      ? (versions.find((version) => version.id === selected.parent_version_id) ?? null)
      : null;
  const aiVersion =
    [...versions].reverse().find((version) => version.source === "ai") ?? null;
  const reasons = reasonsFor(selected);
  const isPublished = submission.published_version_id === selected.id;
  const parentLabel = parent?.source === "ai" ? "AI" : "Previous version";

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href={`/assignments/${assignmentId}`} className="text-xs text-indigo-600 hover:underline">
            ← {submission.assignment_title}
          </Link>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900">
            {submission.student_name}
          </h1>
          <p className="text-sm text-slate-500">
            <span className="font-mono">{submission.student_external_id}</span> · submitted{" "}
            {formatDate(submission.submitted_at)} · {submission.max_points} points possible
          </p>
        </div>
        <Link
          href={`/assignments/${assignmentId}/submissions/${submission.id}/history`}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Version history →
        </Link>
      </div>

      <div className="flex flex-wrap gap-2">
        {versions.map((version) => (
          <Link
            key={version.id}
            href={`/assignments/${assignmentId}/submissions/${submission.id}?version=${version.id}`}
            className={`rounded-full border px-3 py-1 text-xs font-medium ${
              version.id === selected.id
                ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                : "border-slate-300 bg-white text-slate-600 hover:border-slate-400"
            }`}
          >
            #{version.id} · {version.source === "ai" ? "AI" : "Teacher"} ·{" "}
            {formatPoints(version.total_points)}
          </Link>
        ))}
      </div>

      {query.error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {query.error}
        </div>
      ) : null}
      {query.saved ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
          Saved as a new teacher version. The previous version is untouched.
        </div>
      ) : null}
      {isPublished ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          This version is published. Students would see {formatPoints(selected.total_points)}/
          {submission.max_points}.
        </div>
      ) : null}

      {selected.needs_review ? (
        <div className="rounded-xl border-2 border-amber-300 bg-amber-50 p-4">
          <p className="text-sm font-bold uppercase tracking-wide text-amber-900">
            Needs review — publishing is blocked
          </p>
          <p className="mt-1 text-sm text-amber-800">
            The confidence gate flagged this AI version. Save a teacher version to approve or
            correct the scores.
          </p>
          {reasons.length > 0 ? (
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-amber-800">
              {reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <article className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
            Submission
          </h2>
          <div className="mt-3 whitespace-pre-wrap font-serif text-[15px] leading-7 text-slate-800">
            {submission.text}
          </div>
        </article>

        <div className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4 text-xs text-slate-600 shadow-sm">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <span>
                Selected: <strong>#{selected.id}</strong> ·{" "}
                {selected.source === "ai" ? "AI" : "Teacher"}
              </span>
              <span>
                Prompt: <span className="font-mono">{selected.prompt_version || "—"}</span>
              </span>
              <span>
                Author: <span className="font-mono">{selected.created_by}</span>
              </span>
              <span>{formatDate(selected.created_at)}</span>
            </div>
            {aiVersion && aiVersion.id !== selected.id ? (
              <p className="mt-1 text-slate-400">
                AI original: {formatPoints(aiVersion.total_points)} points (#{aiVersion.id})
              </p>
            ) : null}
          </div>

          <form action={saveTeacherVersion} className="space-y-4">
            <input type="hidden" name="assignmentId" value={assignmentId} />
            <input type="hidden" name="submissionId" value={submission.id} />
            <input type="hidden" name="parentVersionId" value={selected.id} />
            <input type="hidden" name="createdBy" value="instructor@example.edu" />

            {selected.criteria.map((score) => {
              const criterion: RubricCriterion | undefined = submission.rubric.find(
                (item) => item.id === score.criterion_id,
              );
              const previous = scoreFor(parent, score.criterion_id);
              const pointsChanged = previous !== null && previous.points !== score.points;
              const justificationChanged =
                previous !== null && previous.justification !== score.justification;
              return (
                <div
                  key={score.criterion_id}
                  className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
                >
                  <input type="hidden" name="criterionId" value={score.criterion_id} />
                  <div className="flex items-baseline justify-between gap-3">
                    <label
                      htmlFor={`points-${score.criterion_id}`}
                      className="text-sm font-semibold text-slate-900"
                    >
                      {score.criterion_name}
                    </label>
                    <div className="flex items-center gap-2">
                      {score.confidence !== null ? (
                        <span
                          className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${
                            score.confidence < 0.65
                              ? "bg-amber-100 text-amber-800"
                              : "bg-slate-100 text-slate-500"
                          }`}
                        >
                          conf {score.confidence.toFixed(2)}
                        </span>
                      ) : null}
                      <span className="text-xs text-slate-400">
                        / {criterion?.max_points ?? "?"}
                      </span>
                      <input
                        id={`points-${score.criterion_id}`}
                        name="points"
                        type="number"
                        min={0}
                        max={criterion?.max_points}
                        step={0.5}
                        defaultValue={score.points}
                        className="w-20 rounded border border-slate-300 px-2 py-1 text-right text-sm tabular-nums focus:border-indigo-500 focus:outline-none"
                      />
                    </div>
                  </div>
                  <label
                    htmlFor={`justification-${score.criterion_id}`}
                    className="mt-2 block text-[11px] font-medium uppercase tracking-wide text-slate-400"
                  >
                    Justification
                  </label>
                  <textarea
                    id={`justification-${score.criterion_id}`}
                    name="justification"
                    rows={3}
                    defaultValue={score.justification}
                    className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
                  />
                  {pointsChanged || justificationChanged ? (
                    <div className="mt-2 rounded bg-indigo-50 px-2 py-1 text-xs text-indigo-800">
                      {pointsChanged ? (
                        <p>
                          {parentLabel} said <strong>{formatPoints(previous?.points ?? null)}</strong>{" "}
                          / you changed to <strong>{formatPoints(score.points)}</strong>
                        </p>
                      ) : null}
                      {justificationChanged ? (
                        <p className="mt-0.5 italic">
                          {parentLabel} said “{previous?.justification}” / you changed to “
                          {score.justification}”
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <label
                htmlFor="summaryComment"
                className="text-sm font-semibold text-slate-900"
              >
                Summary comment
              </label>
              <textarea
                id="summaryComment"
                name="summaryComment"
                rows={4}
                defaultValue={selected.summary_comment}
                className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-sm text-slate-700 focus:border-indigo-500 focus:outline-none"
              />
              {parent !== null && parent.summary_comment !== selected.summary_comment ? (
                <p className="mt-2 rounded bg-indigo-50 px-2 py-1 text-xs italic text-indigo-800">
                  {parentLabel} said “{parent.summary_comment}” / you changed to “
                  {selected.summary_comment}”
                </p>
              ) : null}
            </div>

            <button
              type="submit"
              className="w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-1"
            >
              Save as new version
            </button>
            <p className="text-center text-[11px] text-slate-400">
              Saves an immutable teacher version with parent #{selected.id}. The AI version is
              never modified.
            </p>
          </form>

          <form action={publishVersion} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <input type="hidden" name="assignmentId" value={assignmentId} />
            <input type="hidden" name="submissionId" value={submission.id} />
            <input type="hidden" name="feedbackVersionId" value={selected.id} />
            <input type="hidden" name="publishedBy" value="instructor@example.edu" />
            <button
              type="submit"
              disabled={selected.needs_review}
              title={
                selected.needs_review
                  ? "This version is flagged needs_review and cannot be published"
                  : "Publish this version to the student"
              }
              className="w-full rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-1 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
            >
              {isPublished ? "Republish this version" : "Publish this version"}
            </button>
            {selected.needs_review ? (
              <p className="mt-2 text-center text-xs text-amber-700">
                Blocked: this version needs review. Save a teacher version first.
              </p>
            ) : (
              <p className="mt-2 text-center text-[11px] text-slate-400">
                Publishing version #{selected.id} makes it the official grade. The audit trail
                keeps the full lineage.
              </p>
            )}
          </form>
        </div>
      </div>
    </div>
  );
}
