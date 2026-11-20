"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type Progress = {
  completed: number;
  failed: number;
  total: number;
  status: string;
};

const TERMINAL = new Set(["succeeded", "partial", "failed"]);

export default function RunProgress({
  runId,
  initial,
}: {
  runId: number;
  initial: Progress;
}) {
  const [progress, setProgress] = useState<Progress>(initial);
  const router = useRouter();

  useEffect(() => {
    const source = new EventSource(`/api/events/${runId}`);
    source.onmessage = (event: MessageEvent<string>) => {
      const parsed: unknown = JSON.parse(event.data);
      if (parsed === null || typeof parsed !== "object" || "error" in parsed) {
        source.close();
        return;
      }
      const next = parsed as Progress;
      setProgress(next);
      if (TERMINAL.has(next.status)) {
        source.close();
        router.refresh();
      }
    };
    source.onerror = () => {
      source.close();
    };
    return () => source.close();
  }, [runId, router]);

  const processed = progress.completed + progress.failed;
  const percent =
    progress.total > 0 ? Math.min(100, Math.round((processed / progress.total) * 100)) : 0;
  const done = TERMINAL.has(progress.status);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium text-slate-700">
          Grading run #{runId}{" "}
          <span className="ml-1 font-mono text-xs text-slate-500">{progress.status}</span>
        </span>
        <span className="tabular-nums text-slate-600">
          {processed}/{progress.total} processed
          {progress.failed > 0 ? ` · ${progress.failed} failed` : ""}
        </span>
      </div>
      <div className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all duration-300 ${
            progress.status === "failed"
              ? "bg-red-500"
              : progress.status === "partial"
                ? "bg-amber-500"
                : "bg-indigo-600"
          }`}
          style={{ width: `${done ? 100 : percent}%` }}
        />
      </div>
      <p className="mt-2 text-xs text-slate-500">
        {done
          ? "Run finished — roster refreshed automatically."
          : "Live progress via Server-Sent Events. You can leave this page; the run continues."}
      </p>
    </div>
  );
}
