import Link from "next/link";

import { RunBadge, formatDate } from "@/components/StatusBadge";
import { apiFetch } from "@/lib/api";
import type { AssignmentSummary, GradingRun } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  let assignments: AssignmentSummary[] = [];
  let runs: GradingRun[] = [];
  let error: string | null = null;
  try {
    [assignments, runs] = await Promise.all([
      apiFetch<AssignmentSummary[]>("/assignments"),
      apiFetch<GradingRun[]>("/grading-runs?limit=8"),
    ]);
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">Assignments</h1>
        <p className="mt-1 text-sm text-slate-500">
          Every AI score is versioned. Nothing reaches a student until an instructor publishes it.
        </p>
      </div>

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <p className="font-medium">Could not reach the API.</p>
          <p className="mt-1 font-mono text-xs">{error}</p>
          <p className="mt-2 text-xs">
            Check that the API is running on port 8000 and Postgres is healthy.
          </p>
        </div>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2">
        {assignments.map((assignment) => (
          <Link
            key={assignment.id}
            href={`/assignments/${assignment.id}`}
            className="group rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-indigo-300 hover:shadow"
          >
            <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
              {assignment.course_name}
            </p>
            <h2 className="mt-1 text-lg font-semibold text-slate-900 group-hover:text-indigo-700">
              {assignment.title}
            </h2>
            <div className="mt-4 flex flex-wrap gap-2 text-xs">
              <span className="rounded bg-slate-100 px-2 py-1 font-medium text-slate-700">
                {assignment.graded_count}/{assignment.submission_count} graded
              </span>
              <span className="rounded bg-amber-50 px-2 py-1 font-medium text-amber-800">
                {assignment.needs_review_count} need review
              </span>
              <span className="rounded bg-emerald-50 px-2 py-1 font-medium text-emerald-700">
                {assignment.published_count} published
              </span>
              <span className="rounded bg-slate-50 px-2 py-1 text-slate-500">
                {assignment.max_points} pt rubric
              </span>
            </div>
          </Link>
        ))}
        {!error && assignments.length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-300 p-8 text-sm text-slate-500">
            No assignments yet. Run <code className="font-mono">make seed</code> to load the demo
            course.
          </p>
        ) : null}
      </section>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-500">
          Recent grading runs
        </h2>
        <div className="mt-3 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="min-w-full divide-y divide-slate-100 text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2 font-medium">Run</th>
                <th className="px-4 py-2 font-medium">Assignment</th>
                <th className="px-4 py-2 font-medium">Prompt</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Progress</th>
                <th className="px-4 py-2 font-medium">Finished</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {runs.map((run) => (
                <tr key={run.id} className="text-slate-700">
                  <td className="px-4 py-2 font-mono text-xs">#{run.id}</td>
                  <td className="px-4 py-2">
                    <Link
                      className="hover:text-indigo-700 hover:underline"
                      href={`/assignments/${run.assignment_id}`}
                    >
                      Assignment {run.assignment_id}
                    </Link>
                  </td>
                  <td className="px-4 py-2 font-mono text-xs">{run.prompt_version}</td>
                  <td className="px-4 py-2">
                    <RunBadge status={run.status} />
                  </td>
                  <td className="px-4 py-2 tabular-nums">
                    {run.completed}/{run.total}
                    {run.failed > 0 ? (
                      <span className="ml-1 text-red-600">({run.failed} failed)</span>
                    ) : null}
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-500">
                    {formatDate(run.finished_at)}
                  </td>
                </tr>
              ))}
              {runs.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-sm text-slate-500" colSpan={6}>
                    No grading runs yet.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
