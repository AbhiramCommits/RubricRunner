"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";
import type { FeedbackVersion, GradingRunQueued } from "@/lib/types";

function apiErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    try {
      const parsed: unknown = JSON.parse(error.body);
      if (parsed !== null && typeof parsed === "object" && "detail" in parsed) {
        const detail = (parsed as { detail?: unknown }).detail;
        if (typeof detail === "string") return detail;
      }
    } catch {
      // fall through to the status message
    }
    return `Request failed (${error.status})`;
  }
  return error instanceof Error ? error.message : "Unexpected error";
}

function numberField(formData: FormData, name: string): number {
  const raw = formData.get(name);
  const value = Number(raw);
  if (raw === null || Number.isNaN(value)) {
    throw new Error(`Missing or invalid ${name}`);
  }
  return value;
}

export async function startGradingRun(formData: FormData): Promise<void> {
  const assignmentId = numberField(formData, "assignmentId");
  const promptVersion = String(formData.get("promptVersion") ?? "v2_criterion_anchored");
  let runId: number;
  try {
    const queued = await apiFetch<GradingRunQueued>(
      `/assignments/${assignmentId}/grading-runs`,
      { method: "POST", body: JSON.stringify({ prompt_version: promptVersion }) },
    );
    runId = queued.run_id;
  } catch (error) {
    redirect(`/assignments/${assignmentId}?error=${encodeURIComponent(apiErrorMessage(error))}`);
  }
  revalidatePath(`/assignments/${assignmentId}`);
  redirect(`/assignments/${assignmentId}?run=${runId}`);
}

export async function saveTeacherVersion(formData: FormData): Promise<void> {
  const assignmentId = numberField(formData, "assignmentId");
  const submissionId = numberField(formData, "submissionId");
  const parentVersionId = numberField(formData, "parentVersionId");
  const base = `/assignments/${assignmentId}/submissions/${submissionId}`;

  const criterionIds = formData.getAll("criterionId").map((value) => Number(value));
  const points = formData.getAll("points").map((value) => Number(value));
  const justifications = formData.getAll("justification").map((value) => String(value));
  if (
    criterionIds.length === 0 ||
    criterionIds.length !== points.length ||
    criterionIds.length !== justifications.length ||
    points.some((value) => Number.isNaN(value))
  ) {
    redirect(`${base}?error=${encodeURIComponent("Every criterion needs a numeric score")}`);
  }

  let saved: FeedbackVersion;
  try {
    saved = await apiFetch<FeedbackVersion>(`/submissions/${submissionId}/feedback-versions`, {
      method: "POST",
      body: JSON.stringify({
        parent_version_id: parentVersionId,
        summary_comment: String(formData.get("summaryComment") ?? ""),
        created_by: String(formData.get("createdBy") ?? "instructor@example.edu"),
        criteria: criterionIds.map((criterionId, index) => ({
          criterion_id: criterionId,
          points: points[index] ?? 0,
          justification: justifications[index] ?? "",
        })),
      }),
    });
  } catch (error) {
    redirect(`${base}?error=${encodeURIComponent(apiErrorMessage(error))}`);
  }

  revalidatePath(`/assignments/${assignmentId}`);
  revalidatePath(base);
  revalidatePath(`${base}/history`);
  redirect(`${base}?version=${saved.id}&saved=1`);
}

export async function publishVersion(formData: FormData): Promise<void> {
  const assignmentId = numberField(formData, "assignmentId");
  const submissionId = numberField(formData, "submissionId");
  const versionId = numberField(formData, "feedbackVersionId");
  const base = `/assignments/${assignmentId}/submissions/${submissionId}`;
  try {
    await apiFetch(`/submissions/${submissionId}/publish`, {
      method: "POST",
      body: JSON.stringify({
        feedback_version_id: versionId,
        published_by: String(formData.get("publishedBy") ?? "instructor@example.edu"),
      }),
    });
  } catch (error) {
    redirect(`${base}?version=${versionId}&error=${encodeURIComponent(apiErrorMessage(error))}`);
  }
  revalidatePath(`/assignments/${assignmentId}`);
  revalidatePath(base);
  revalidatePath(`${base}/history`);
  redirect(`/assignments/${assignmentId}?published=${submissionId}`);
}
