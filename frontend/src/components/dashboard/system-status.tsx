"use client";

import { useSystemStatus, type StatusState, type SystemStatusItem } from "@/hooks/use-system-status";
import { RefreshCw } from "lucide-react";

const DOT: Record<StatusState, string> = {
  active: "bg-green-500",
  down: "bg-red-500",
  disabled: "bg-muted-foreground/30",
};
const TEXT: Record<StatusState, string> = {
  active: "text-muted-foreground",
  down: "text-red-500",
  disabled: "text-muted-foreground",
};

function Row({ it }: { it: SystemStatusItem }) {
  return (
    <div className="flex items-center gap-2.5 text-sm">
      <span className={`h-2.5 w-2.5 rounded-full shrink-0 ${DOT[it.state]}`} />
      <span className="text-foreground">{it.label}</span>
      <span className={`ml-auto text-xs ${TEXT[it.state]}`}>{it.detail}</span>
    </div>
  );
}

function Group({ title, items }: { title: string; items: SystemStatusItem[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{title}</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
        {items.map((it) => <Row key={it.key} it={it} />)}
      </div>
    </div>
  );
}

export function SystemStatusPanel() {
  const { data, isLoading } = useSystemStatus();
  const items = data?.items ?? [];
  const core = items.filter((i) => i.group === "core");
  const platform = items.filter((i) => i.group === "platform");
  const delivery = items.filter((i) => i.group === "delivery");

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-foreground">System status</h3>
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <RefreshCw className="h-3 w-3" /> auto
        </span>
      </div>
      {isLoading ? (
        <div className="py-6 text-center text-sm text-muted-foreground">Checking…</div>
      ) : (
        <div className="space-y-4">
          <Group title="Core" items={core} />
          <Group title="Platforms" items={platform} />
          <Group title="Delivery" items={delivery} />
        </div>
      )}
      <div className="mt-4 flex gap-4 border-t border-border pt-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-green-500" />Active</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-red-500" />Down</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-muted-foreground/30" />Not enabled</span>
      </div>
    </div>
  );
}
