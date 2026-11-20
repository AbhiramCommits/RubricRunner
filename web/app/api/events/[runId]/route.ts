import { API_BASE_URL } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ runId: string }> },
): Promise<Response> {
  const { runId } = await params;
  const upstream = await fetch(`${API_BASE_URL}/grading-runs/${runId}/events`, {
    headers: { Accept: "text/event-stream" },
    cache: "no-store",
  });
  if (!upstream.ok || upstream.body === null) {
    return new Response(`Upstream grading run unavailable (${upstream.status})`, {
      status: 502,
      headers: { "Content-Type": "text/plain" },
    });
  }
  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
