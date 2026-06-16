"use client";

import { useState } from "react";
import { Bot, CheckCircle, ThumbsDown, ThumbsUp, Sparkles, X, AlertTriangle, Info, AlertCircle, Loader2 } from "lucide-react";
import {
  useAIInsights,
  useGenerateInsight,
  useDismissInsight,
  useInsightFeedback,
} from "@/hooks/use-ai-insights";
import type { AIInsight, InsightSeverity, InsightType } from "@/types/ai-insight";
import { INSIGHT_TYPES, INSIGHT_TYPE_LABELS } from "@/types/ai-insight";

const SEVERITY_CONFIG: Record<InsightSeverity, { icon: React.ReactNode; cls: string }> = {
  info: { icon: <Info className="h-4 w-4" />, cls: "text-blue-400 bg-blue-500/10 border-blue-500/20" },
  warning: { icon: <AlertTriangle className="h-4 w-4" />, cls: "text-yellow-400 bg-yellow-500/10 border-yellow-500/20" },
  critical: { icon: <AlertCircle className="h-4 w-4" />, cls: "text-red-400 bg-red-500/10 border-red-500/20" },
};

function ConfidenceBadge({ score }: { score: string }) {
  const pct = Math.round(parseFloat(score) * 100);
  const color = pct >= 80 ? "text-green-400 bg-green-500/10" : pct >= 50 ? "text-yellow-400 bg-yellow-500/10" : "text-red-400 bg-red-500/10";
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${color}`}>
      {pct}% confidence
    </span>
  );
}

function InsightCard({
  insight,
  onDismiss,
  onFeedback,
}: {
  insight: AIInsight;
  onDismiss: (id: string) => void;
  onFeedback: (id: string, helpful: boolean) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const sev = SEVERITY_CONFIG[insight.severity];

  return (
    <div className={`border border-border rounded-lg p-4 space-y-3 bg-card ${insight.is_dismissed ? "opacity-40" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2 flex-1">
          <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded border font-medium ${sev.cls}`}>
            {sev.icon}
            {insight.severity.toUpperCase()}
          </span>
          <div className="flex-1">
            <p className="text-sm font-semibold leading-tight">{insight.title}</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {INSIGHT_TYPE_LABELS[insight.insight_type] ?? insight.insight_type}
              {insight.period_start && ` · ${insight.period_start} → ${insight.period_end}`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <ConfidenceBadge score={insight.confidence_score} />
          {!insight.is_dismissed && (
            <button
              onClick={() => onDismiss(insight.id)}
              className="text-muted-foreground hover:text-foreground p-1 rounded"
              title="Dismiss"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      <p className="text-sm text-muted-foreground leading-relaxed">{insight.summary}</p>

      {expanded && (
        <div className="text-xs text-muted-foreground bg-muted/30 rounded p-3 leading-relaxed whitespace-pre-wrap">
          {insight.explanation}
        </div>
      )}

      <div className="flex items-center gap-3 pt-1">
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-primary underline-offset-2 hover:underline"
        >
          {expanded ? "Show less" : "Show explanation"}
        </button>
        {!insight.is_dismissed && (
          <div className="flex items-center gap-1 ml-auto">
            <span className="text-xs text-muted-foreground mr-1">Helpful?</span>
            <button
              onClick={() => onFeedback(insight.id, true)}
              className={`p-1 rounded ${insight.is_helpful === true ? "text-green-400" : "text-muted-foreground hover:text-green-400"}`}
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => onFeedback(insight.id, false)}
              className={`p-1 rounded ${insight.is_helpful === false ? "text-red-400" : "text-muted-foreground hover:text-red-400"}`}
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function GenerateForm() {
  const defaults = (() => {
    const end = new Date().toISOString().slice(0, 10);
    const d = new Date();
    d.setDate(1);
    return { start: d.toISOString().slice(0, 10), end };
  })();

  const [type, setType] = useState<InsightType>("pnl_summary");
  const [start, setStart] = useState(defaults.start);
  const [end, setEnd] = useState(defaults.end);
  const { mutate, isPending, isSuccess } = useGenerateInsight();

  return (
    <div className="border border-border rounded-lg p-4 bg-card space-y-3">
      <p className="text-sm font-medium flex items-center gap-1.5">
        <Sparkles className="h-4 w-4 text-primary" />
        Generate AI Insight
      </p>
      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs font-medium block mb-1">Type</label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as InsightType)}
            className="text-sm border border-input rounded-md px-2 py-1.5 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
          >
            {INSIGHT_TYPES.map((t) => (
              <option key={t} value={t}>{INSIGHT_TYPE_LABELS[t]}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">From</label>
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)}
            className="text-sm border border-input rounded-md px-3 py-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary" />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider block mb-1.5">To</label>
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
            className="text-sm border border-input rounded-md px-3 py-2 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary" />
        </div>
        <button
          onClick={() => mutate({ insight_type: type, period_start: start, period_end: end })}
          disabled={isPending || !start || !end}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold bg-primary text-primary-foreground rounded-md disabled:opacity-50 hover:bg-primary/90 transition-colors"
        >
          {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Bot className="h-3.5 w-3.5" />}
          {isPending ? "Queuing…" : "Generate"}
        </button>
      </div>
      {isSuccess && (
        <p className="text-xs text-green-400 flex items-center gap-1">
          <CheckCircle className="h-3.5 w-3.5" />
          Queued — insight will appear shortly.
        </p>
      )}
    </div>
  );
}

export default function InsightsPage() {
  const [typeFilter, setTypeFilter] = useState<InsightType | "">("");
  const [showDismissed, setShowDismissed] = useState(false);

  const { data, isLoading } = useAIInsights({
    insight_type: typeFilter || undefined,
    include_dismissed: showDismissed,
  });
  const { mutate: dismiss } = useDismissInsight();
  const { mutate: feedback } = useInsightFeedback();

  const insights = data?.data ?? [];

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">AI Insights</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Claude-powered financial analysis. Insights read financial data — never modify records.
        </p>
      </div>

      <GenerateForm />

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value as InsightType | "")}
          className="text-sm border border-input rounded-md px-2 py-1.5 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
        >
          <option value="">All types</option>
          {INSIGHT_TYPES.map((t) => (
            <option key={t} value={t}>{INSIGHT_TYPE_LABELS[t]}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-xs cursor-pointer">
          <input
            type="checkbox"
            checked={showDismissed}
            onChange={(e) => setShowDismissed(e.target.checked)}
          />
          Show dismissed
        </label>
        {data && (
          <span className="text-xs text-muted-foreground ml-auto">
            {data.meta.total} insight{data.meta.total !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading insights…</p>}

      {!isLoading && insights.length === 0 && (
        <div className="border rounded-lg p-8 text-center space-y-2">
          <Bot className="h-10 w-10 mx-auto text-muted-foreground opacity-40" />
          <p className="text-sm text-muted-foreground">No insights yet. Generate one above.</p>
        </div>
      )}

      <div className="space-y-3">
        {insights.map((insight) => (
          <InsightCard
            key={insight.id}
            insight={insight}
            onDismiss={(id) => dismiss(id)}
            onFeedback={(id, helpful) => feedback({ insightId: id, isHelpful: helpful })}
          />
        ))}
      </div>
    </div>
  );
}
