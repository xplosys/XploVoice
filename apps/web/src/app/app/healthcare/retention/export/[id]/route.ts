// XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
// Downloads an approved access request's export. The API checks phi:read and writes the PHI access log.
import { api, ApiError } from "@/lib/api";

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const data = await api<unknown>(`/v1/retention/requests/${encodeURIComponent(id)}/export`);
    return new Response(JSON.stringify(data, null, 2), {
      headers: {
        "Content-Type": "application/json",
        "Content-Disposition": `attachment; filename="access-request-${id.slice(0, 8)}.json"`,
        "Cache-Control": "no-store",
      },
    });
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 502;
    return new Response(e instanceof ApiError ? e.message : "Unavailable", { status });
  }
}
