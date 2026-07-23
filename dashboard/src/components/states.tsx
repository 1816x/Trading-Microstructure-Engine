import type { ReactNode } from "react";

import type { ApiError } from "@/lib/api";

/** Full-width failure card, surfacing the backend's own `detail` message. */
export function ErrorState({ error, hint }: { error: ApiError; hint?: ReactNode }) {
  return (
    <div className="rounded-lg border border-hairline bg-surface p-6">
      <h2 className="text-sm font-medium">
        {error.status > 0 ? `Backend replied ${error.status}` : "Backend unreachable"}
      </h2>
      <p className="mt-2 text-sm text-ink-2">{error.detail}</p>
      {hint ? <div className="mt-3 text-xs text-muted">{hint}</div> : null}
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body?: ReactNode }) {
  return (
    <div className="rounded-lg border border-hairline bg-surface p-6">
      <h2 className="text-sm font-medium">{title}</h2>
      {body ? <div className="mt-2 text-sm text-ink-2">{body}</div> : null}
    </div>
  );
}
