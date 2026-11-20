// Mirrored by hand from the FastAPI OpenAPI schema (`/openapi.json`).
// See README "Architecture" for the contract-sync approach. Run `make api-openapi`
// to regenerate `openapi.json` and compare before changing these types.

export interface RubricCriterion {
  id: number;
  assignment_id: number;
  name: string;
  description: string;
  max_points: number;
  weight: number;
  order_index: number;
}

export interface AssignmentSummary {
  id: number;
  course_id: number;
  course_name: string;
  title: string;
  max_points: number;
  submission_count: number;
  graded_count: number;
  needs_review_count: number;
  published_count: number;
  created_at: string;
}

export interface Assignment {
  id: number;
  course_id: number;
  course_name: string;
  title: string;
  prompt_text: string;
  max_points: number;
  created_at: string;
  criteria: RubricCriterion[];
}

export interface CriterionScore {
  id: number;
  criterion_id: number;
  criterion_name: string;
  points: number;
  confidence: number | null;
  justification: string;
}

export interface FeedbackVersion {
  id: number;
  submission_id: number;
  grading_run_id: number | null;
  source: "ai" | "teacher";
  parent_version_id: number | null;
  summary_comment: string;
  total_points: number;
  needs_review: boolean;
  raw_model_output: Record<string, unknown> | null;
  prompt_version: string;
  created_by: string;
  created_at: string;
  criteria: CriterionScore[];
}

export type RosterStatus =
  | "ungraded"
  | "ai_graded"
  | "needs_review"
  | "teacher_edited"
  | "published";

export interface RosterEntry {
  student_id: number;
  submission_id: number;
  external_id: string;
  name: string;
  status: RosterStatus;
  ai_total: number | null;
  current_total: number | null;
  lowest_confidence: number | null;
  published_version_id: number | null;
}

export interface Submission {
  id: number;
  assignment_id: number;
  assignment_title: string;
  student_id: number;
  student_name: string;
  student_external_id: string;
  text: string;
  submitted_at: string;
  max_points: number;
  rubric: RubricCriterion[];
  versions: FeedbackVersion[];
  published_version_id: number | null;
}

export interface GradingRunOutcome {
  submission_id: number;
  student_name: string;
  student_external_id: string;
  status: string;
  attempts: number;
  error: string | null;
  feedback_version_id: number | null;
  needs_review: boolean | null;
  total_points: number | null;
}

export interface GradingRun {
  id: number;
  assignment_id: number;
  prompt_version: string;
  provider: string;
  model: string;
  status: "queued" | "running" | "succeeded" | "partial" | "failed";
  total: number;
  completed: number;
  failed: number;
  started_at: string | null;
  finished_at: string | null;
  error_summary: string | null;
  duration_seconds: number | null;
  outcomes: GradingRunOutcome[];
}

export interface GradingRunQueued {
  run_id: number;
  status: string;
}

export interface PublishedGrade {
  id: number;
  submission_id: number;
  feedback_version_id: number;
  published_at: string;
  published_by: string;
}

export interface AuditTrail {
  submission_id: number;
  published: PublishedGrade;
  chain: FeedbackVersion[];
}
