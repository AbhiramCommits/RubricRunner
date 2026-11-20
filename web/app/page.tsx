import { getHealth } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let db = "down";
  let reachable = false;
  let error: string | null = null;
  try {
    const health = await getHealth();
    reachable = health.status === "ok";
    db = health.db;
  } catch (err) {
    error = err instanceof Error ? err.message : String(err);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Service status</h1>
        <p className="mt-1 text-sm text-slate-500">
          RubricRunner API and Postgres connectivity, read by a Next.js server component.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <StatusCard label="API" ok={reachable} detail={reachable ? "reachable" : "unreachable"} />
        <StatusCard label="Postgres" ok={db === "ok"} detail={db} />
      </div>

      {error ? (
        <pre className="overflow-x-auto rounded-lg border border-red-200 bg-red-50 p-4 text-xs text-red-700">
          {error}
        </pre>
      ) : null}
    </div>
  );
}

function StatusCard({ label, ok, detail }: { label: string; ok: boolean; detail: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-600">{label}</span>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
            ok ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
          }`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`} />
          {detail}
        </span>
      </div>
    </div>
  );
}
