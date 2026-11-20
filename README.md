# RubricRunner

Auditable, AI-assisted assignment feedback for instructors.

## 1. What RubricRunner does

An instructor creates an assignment with a weighted rubric, imports a class roster with each
student's submission, and starts one batch grading run against a named prompt version. The grader
returns per-criterion scores with confidences and justifications; low-confidence or borderline
results are forced into human review instead of being auto-published. The instructor opens a
student, sees the AI's score next to their own edit, and saves a new teacher version without ever
mutating the AI's version. Only a teacher-approved version can be published, and the published
grade retains a complete lineage back to the exact model output and prompt version that produced
it. RubricRunner is built for high-school and college instructors and teaching teams who grade
writing at scale but cannot hand-wave the audit trail.

> **The guarantee:** no grade reaches a student without a teacher-approved version, and every
> published grade is auditable back to the model output and prompt version that produced it.

## 2. Architecture

```text
┌───────────────────────────────────────────────────────────────┐
│ Browser                                                       │
│  Next.js 15 App Router (port 3000)                            │
│   • server components read through apiFetch (no client fetch) │
│   • server actions write + revalidatePath                     │
│   • RunProgress subscribes to same-origin SSE proxy           │
└───────────────┬───────────────────────────────┬───────────────┘
                │ REST (server-side)            │ GET /api/events/:runId
                ▼                               ▼ (streams upstream)
┌───────────────────────────────────────────────────────────────┐
│ FastAPI (port 8000)                                           │
│  routers: assignments · submissions · feedback · grading      │
│  grading queue: asyncio pool (4 workers), grading_runs table  │
│  providers: Anthropic | OpenAI | deterministic MockProvider   │
└───────────────┬───────────────────────────────────────────────┘
                │ SQLAlchemy 2.x
                ▼
┌───────────────────────────────────────────────────────────────┐
│ PostgreSQL 16                                                 │
│  courses · assignments · rubric_criteria · students ·         │
│  submissions · grading_runs · grading_run_items ·             │
│  feedback_versions · criterion_scores · published_grades      │
└───────────────▲───────────────────────────────────────────────┘
                │ reads the same submissions and prompt registry
┌───────────────┴───────────────────────────────────────────────┐
│ eval/run_eval.py (offline)                                    │
│  MockProvider → 12 hand-labeled submissions → eval/results/*  │
└───────────────────────────────────────────────────────────────┘
```

### Data model

| Table | Purpose |
|---|---|
| `courses`, `assignments`, `rubric_criteria` | The assignment and its rubric, ordered by `order_index`. |
| `students`, `submissions` | Roster and prose submissions, unique per `(assignment, student)`. |
| `grading_runs` | Durable run state: `queued → running → succeeded / partial / failed`, counters, timestamps, error summary. |
| `grading_run_items` | Per-submission outcome for a run (attempts, error, produced version). Supporting table for partial-failure reporting. |
| `feedback_versions` | Append-only grade versions: `source` (`ai`/`teacher`), `parent_version_id`, totals, `needs_review`, `raw_model_output` (JSONB), `prompt_version`, author. |
| `criterion_scores` | Per-criterion points, confidence, and justification owned by exactly one feedback version. |
| `published_grades` | One row per submission (`UNIQUE`), pointing at the version the student sees. |

### Versioning and lineage rules

- **Versions are append-only.** No code path updates or deletes an existing
  `feedback_versions` row or its `criterion_scores`.
- An **AI version** has `parent_version_id = NULL`, `source = ai`, a `prompt_version`, and the
  exact `raw_model_output` (raw text, parsed result, attempts, review reasons).
- A **teacher version** points `parent_version_id` at the version being edited,
  `source = teacher`, `needs_review = false`, and inherits the parent's `prompt_version` so the
  model provenance survives the edit.
- **Publishing** updates the single `published_grades` row to point at a chosen version. The API
  returns `409` if that version has `needs_review = true`.
- **Audit trail** (`GET /submissions/{id}/audit-trail`) walks `parent_version_id` from the
  published version back to the originating AI version and includes each version's raw model
  output and prompt version.
- The roster status is derived, never stored: `ungraded`, `ai_graded`, `needs_review`,
  `teacher_edited`, `published` (published only when the published version is still the latest).

### Confidence gate (exact thresholds)

After validation, an AI version is flagged `needs_review = true` when **any** of these is true:

1. any criterion has `confidence < 0.65`;
2. the total is within **1.0 point** of the pass boundary, defined as
   `0.60 × assignment.max_points` (15 of 25 for the demo assignment);
3. the output needed a schema-repair retry.

Publishing a flagged version is blocked by the API with HTTP 409 and the UI disables the publish
button. Saving a teacher version clears the flag because the teacher has then approved the score.

### Retries and partial-failure runs

- **Structured-output repair:** a parse or `GradeResult` validation failure is retried up to 3
  total model calls, with the validator error appended as a repair instruction. Exhausting all
  three raises `GradingError`.
- **Per-submission retry:** the batch runner attempts each submission up to 3 times with
  exponential backoff (0.25s, then 0.5s).
- **Run outcome:** one submission failing never aborts the run. `failed == 0` → `succeeded`;
  `0 < failed < total` → `partial`; `failed == total` → `failed`. Every run item records attempts
  and the error.
- **Restart safety:** run state lives in Postgres. A run left `running` is requeued at startup;
  successes already tied to the run are reconciled from `feedback_versions`, so completed
  submissions are not graded twice.

## 3. How to run

Prerequisites: Python 3.11, Node.js 20+, Docker, `make`.

```bash
git clone <repo-url> RubricRunner
cd RubricRunner
cp .env.example .env
make install                 # creates api/.venv and runs npm install
docker compose up -d postgres
make migrate                 # Alembic → latest schema
make seed                    # idempotent demo course: 24 students + submissions
```

Run the services in two terminals:

```bash
make api-dev                 # http://localhost:8000 (reload)
make web-dev                 # http://localhost:3000
```

Notes:

- Postgres is exposed on host port **5434** (container 5432) because 5432 is commonly occupied
  by a local Postgres. The URL in `.env.example` matches.
- `make seed` is idempotent: it replaces the demo course and resets identity sequences, so
  assignment #1 stays assignment #1 across re-runs.

### Full stack with Docker Compose

```bash
docker compose up -d --build
docker compose exec api python -m seed
```

The API container runs `alembic upgrade head` before starting. The web app is at
`http://localhost:3000` and reaches the API at `http://api:8000`; browser SSE goes through a
same-origin Next.js proxy, so it works inside Compose too.

### Tests and eval

```bash
make test                    # pytest: API + grading + queue + eval metrics
make test-e2e                # Playwright (API, web and Postgres must be up)
make eval                    # writes eval/results/<version>.json + summary.md
```

`make test-e2e` uses Playwright's `webServer` config to start the API and web app if they are not
already running; Postgres must be up and migrated. The single spec reseeds the demo database at
the start, grades the class, edits two criteria, saves, publishes, and checks the history and
audit trail.

### Switching LLM provider

`LLM_PROVIDER=mock` is the default and is used for tests, CI, and every number below. To use a
real provider, set it in `.env`:

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
# optional overrides
ANTHROPIC_MODEL=claude-sonnet-4-5
```

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

The provider abstraction is one blocking `complete(system, user) -> str` call; Anthropic and
OpenAI adapters are thin wrappers over the official SDKs. No code changes are needed to switch.

### Type contract

`web/lib/types.ts` is **hand-mirrored** from the FastAPI OpenAPI schema. The generated contract is
committed as `openapi.json` and can be refreshed with:

```bash
make api-openapi
```

We chose mirroring over a codegen step so the web build has no Python/codegen dependency.
Runtime validation remains authoritative in Pydantic v2.

## 4. Results

All figures below were produced by this build with the deterministic `MockProvider` and the
12 hand-labeled submissions in `eval/data/gold_scores.json`.

### Eval: per-criterion exact and within-1 agreement

| Prompt | Thesis exact | Evidence exact | Organization exact | Mechanics exact | Thesis ±1 | Evidence ±1 | Organization ±1 | Mechanics ±1 |
|---|---|---|---|---|---|---|---|---|
| `v1_basic` | 17% | 0% | 33% | 42% | 58% | 25% | 92% | 100% |
| `v2_criterion_anchored` | 33% | 17% | 25% | 42% | 58% | 50% | 83% | 92% |

### Eval: per-criterion MAE and totals

| Prompt | Thesis MAE | Evidence MAE | Organization MAE | Mechanics MAE | Overall MAE | Total-score MAE |
|---|---|---|---|---|---|---|
| `v1_basic` | 1.50 | 2.17 | 0.75 | 0.58 | 1.25 | 4.00 |
| `v2_criterion_anchored` | 1.17 | 1.50 | 0.92 | 0.67 | 1.06 | 2.08 |

### Eval: aggregate metrics

| Prompt | n | Pearson (totals) | Spearman (totals) | Rubric adherence | Needs-review rate | Flagged items off by >1 |
|---|---|---|---|---|---|---|
| `v1_basic` | 12 | 0.914 | 0.918 | 100% | 92% (11/12) | 91% (10/11) |
| `v2_criterion_anchored` | 12 | 0.928 | 0.894 | 100% | 50% (6/12) | 50% (3/6) |

**Which prompt won:** `v2_criterion_anchored` won on total-score MAE (2.08 vs 4.00, better by
1.92 points), overall criterion MAE (1.06 vs 1.25), and evidence within-1 agreement (50% vs 25%,
+25 points); `v1_basic` won on Spearman rank correlation (0.918 vs 0.894), organization exact
match (33% vs 25%), and organization within-1 agreement (92% vs 83%).

### Batch grading run (Step 4)

| Metric | Value |
|---|---|
| Submissions graded | 24 |
| Completed | 24 |
| Failed | 0 |
| Status | `succeeded` |
| Needs review | 15 of 24 |
| Wall-clock | 0.52 s |
| Worker concurrency | 4 |

### Injected-failure run

| Metric | Value |
|---|---|
| Total | 24 |
| Completed | 22 |
| Failed | 2 (S17, S18; 3 attempts each) |
| Status | `partial` |

### Tests

| Suite | Count | Result |
|---|---|---|
| pytest | 25 tests | all passed |
| Coverage (`pytest --cov=app`) | 91% | 1222 statements, 106 missed |
| Playwright | 1 spec | passed (grade → edit 2 criteria → save → publish → history/audit) |

### Repository size

Command used:

```bash
git ls-files '*.py' | xargs wc -l | tail -1
git ls-files '*.ts' '*.tsx' | xargs wc -l | tail -1
```

- Python: **4,846 lines** (API, tests, seed, eval harness)
- TypeScript/TSX: **1,464 lines** (Next.js app, components, lib, Playwright spec)

## 5. Design tradeoffs and what I'd do next

- **In-process asyncio queue instead of Celery/Redis.** The queue is durable in Postgres and uses
  `SELECT … FOR UPDATE SKIP LOCKED`, so a restart does not lose work and there is no broker to
  operate. The cost is that workers share the API process and cannot scale across replicas
  without moving the runner to a dedicated process.
- **Append-only versions instead of mutable grades.** Every save creates a row, which makes the
  audit trail trivial to prove and impossible to rewrite. The tradeoff is more rows and the need
  to derive "current" state from the latest version and the published pointer.
- **MockProvider as the CI oracle.** It is deterministic, needs no keys, and exercises the real
  prompt registry and validator. But it is a heuristic simulator, not a model-quality signal: its
  sensitivity to prompt detail is engineered, and its agreement numbers should not be read as
  Anthropic/OpenAI performance.
- **Conservative confidence gate.** The gate flagged 15 of 24 submissions in the demo run and
  6 of 12 gold essays. That is high recall and low precision (50% of flagged items were genuinely
  off by more than 1 point under v2). In production I would tune on a larger labeled set and add
  teacher dispositions ("agree/disagree with flag") as feedback labels.
- **Hand-mirrored TypeScript types.** This keeps the web build free of codegen and Python
  dependencies. The risk is drift; committing `openapi.json` and running `make api-openapi` during
  review is the current mitigation, and generated types would be the next step.
- **Synchronous SQLAlchemy inside `asyncio.to_thread`.** Simple and correct at class scale
  (24 submissions in 0.52 s), but it blocks a worker thread per call. At higher volume I would
  split into a separate worker service and use async SQLAlchemy or a task queue.
- **SSE backed by 0.2 s polling.** The SSE endpoint polls the run row and emits on change. It is
  easy to reason about and survives restarts, but Postgres `LISTEN/NOTIFY` or Redis pub/sub would
  cut the polling traffic.
- **Small, single-instructor gold set.** Twelve essays labelled by one instructor make the eval
  directional. Next I would add a second rater, measure inter-rater agreement, and grow the gold
  set before trusting small differences between prompt versions.
- **No authentication/authorization yet.** The demo assumes one trusted instructor. A real
  deployment needs SSO, course-level permissions, and an audit of who published what (the schema
  already stores `published_by` and `created_by`).

## License

MIT — see [LICENSE](LICENSE).
