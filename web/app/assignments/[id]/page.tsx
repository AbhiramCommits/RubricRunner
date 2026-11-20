import Link from "next/link";
import { notFound } from "next/navigation";

import { startGradingRun } from "@/app/actions";
import RunProgress from "@/app/assignments/[id]/RunProgress";
import { RunBadge, StatusBadge, formatDate, formatPoints } from "@/components/StatusBadge";
import { apiFetch } from "@/lib/api";
import type { Assignment, GradingRun, RosterEntry } from "@/lib/types";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{
    run?: string;
    error?: string;
    published?: string;
    saved?: string;
  }>;
};

export default async function AssignmentPage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const query = await searchParams;
  const assignmentId = Number(id);
  if (Number.isNaN(assignmentId)) notFound();

  let assignment: Assignment;
  let roster: RosterEntry[];
  try {
    [assignment, roster] = await Promise.all([
      apiFetch<Assignment>(`/assignments/${assignmentId}`),
      apiFetch<RosterEntry[]>(`/assignments/${assignmentId}/roster`),
    ]);
  } catch {
    notFound();
  }

  let run: GradingRun | null = null;
  if (query.run) {
    try {
      run = await apiFetch<GradingRun>(`/grading-runs/${query.run}`);
    } catch {
      run = null;
    }
  }

  let recentRuns: GradingRun[] = [];
  try {
    const all = await apiFetch<GradingRun[]>("/grading-runs?limit=20");
    recentRuns = all.filter((item) => item.assignment_id === assignmentId).slice(0, 5);
  } catch {
    recentRuns = [];
  }

  const counts = {
    graded: roster.filter((entry) => entry.status !== "ungraded").length,
    review: roster.filter((entry) => entry.status === "needs_review").length,
    published: roster.filter((entry) => entry.status === "published").length,
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link href="/" className="text-xs text-indigo-600 hover:underline">
            ← All assignments
          </Link>
          <p className="mt-2 text-xs font-medium uppercase tracking-wider text-slate-400">
            {assignment.course_name}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
            {assignment.title}
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-600">{assignment.prompt_text}</p>
        </div>
        <div className="flex flex-col items-end gap-3">
          <div className="flex gap-2 text-xs">
            <span className="rounded bg-slate-100 px-2 py-1 font-medium text-slate-700">
              {counts.graded}/{roster.length} graded
            </span>
            <span className="rounded bg-amber-50 px-2 py-1 font-medium text-amber-800">
              {counts.review} need review
            </span>
            <span className="rounded bg-emerald-50 px-2 py-1 font-medium text-emerald-700">
              {counts.published} published
            </span>
          </div>
          <form action={startGradingRun} className="flex items-center gap-2">
            <input type="hidden" name="assignmentId" value={assignmentId} />
            <label className="sr-only" htmlFor="promptVersion">
              Prompt version
            </label>
            <select
              id="promptVersion"
              name="promptVersion"
              defaultValue="v2_criterion_anchored"
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none"
            >
              <option value="v2_criterion_anchored">v2 · criterion anchored</option>
              <option value="v1_basic">v1 · basic</option>
            </select>
            <button
              type="submit"
              className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:ring-offset-1"
            >
              Grade whole class
            </button>
          </form>
        </div>
      </div>

      {query.error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {query.error}
        </div>
      ) : null}
      {query.published ? (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
          Grade published. The roster now shows the published version.
        </div>
      ) : null}

      {run ? (
        <RunProgress
          runId={run.id}
          initial={{
            completed: run.completed,
            failed: run.failed,
            total: run.total,
            status: run.status,
          }}
        />
      ) : null}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-full divide-y divide-slate-100 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2.5 font-medium">Student</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 text-right font-medium">AI total</th>
              <th className="px-4 py-2.5 text-right font-medium">Current total</th>
              <th className="px-4 py-2.5 text-right font-medium">Lowest conf.</th>
              <th className="px-4 py-2.5" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {roster.map((entry) => (
              <tr key={entry.student_id} className="hover:bg-slate-50">
                <td className="px-4 py-2.5">
                  <div className="font-medium text-slate-900">{entry.name}</div>
                  <div className="font-mono text-xs text-slate-400">{entry.external_id}</div>
                </td>
                <td className="px-4 py-2.5">
                  <StatusBadge status={entry.status} />
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums text-slate-600">
                  {formatPoints(entry.ai_total)}
                </td>
                <td className="px-4 py-2.5 text-right font-medium tabular-nums text-slate-900">
                  {formatPoints(entry.current_total)}
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums">
                  {entry.lowest_confidence === null ? (
                    <span className="text-slate-400">—</span>
                  ) : (
                    <span
                      className={
                        entry.lowest_confidence < 0.65
                          ? "font-semibold text-amber-700"
                          : "text-slate-600"
                      }
                    >
                      {entry.lowest_confidence.toFixed(2)}
                    </span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <Link
                    href={`/assignments/${assignmentId}/submissions/${entry.submission_id}`}
                    className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-white"
                  >
                    Review
                  </Link>
                </td>
              </tr>
            ))}
            {roster.length === 0 ? (
              <tr>
                <td className="px-4 py-8 text-center text-sm text-slate-500" colSpan={6}>
                  No submissions imported for this assignment.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {recentRuns.length > 0 ? (
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
            Runs for this assignment
          </h2>
          <ul className="mt-2 space-y-2">
            {recentRuns.map((item) => (
              <li
                key={item.id}
                className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm"
              >
                <span className="font-mono text-xs text-slate-500">#{item.id}</span>
                <RunBadge status={item.status} />
                <span className="font-mono text-xs">{item.prompt_version}</span>
                <span className="tabular-nums text-slate-600">
                  {item.completed}/{item.total} graded
                  {item.failed > 0 ? ` · ${item.failed} failed` : ""}
                </span>
                <span className="text-xs text-slate-400">
                  {item.duration_seconds !== null ? `${item.duration_seconds.toFixed(2)}s` : "—"}
                </span>
                <span className="ml-auto text-xs text-slate-400">
                  {formatDate(item.finished_at)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
