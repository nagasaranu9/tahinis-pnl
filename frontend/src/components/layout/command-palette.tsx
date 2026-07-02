"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import {
  LayoutDashboard, FileText, DollarSign, GitMerge, TrendingUp, Bot,
  Settings, Building2, Megaphone, Zap, Activity, Star, Search, Moon, Sun,
} from "lucide-react";

interface Command {
  label: string;
  group: string;
  icon: React.ComponentType<{ className?: string }>;
  href?: string;
  action?: () => void;
  keywords?: string;
}

/**
 * Global command palette. Cmd/Ctrl+K toggles it; type to filter, arrows to
 * move, Enter to run. Navigation + a couple of quick actions (theme toggle).
 */
export function CommandPalette() {
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const commands = useMemo<Command[]>(
    () => [
      { label: "Dashboard", group: "Go to", icon: LayoutDashboard, href: "/dashboard" },
      { label: "P&L Reports", group: "Finance", icon: TrendingUp, href: "/pnl", keywords: "profit loss" },
      { label: "Expenses", group: "Finance", icon: DollarSign, href: "/expenses" },
      { label: "Reconciliation", group: "Finance", icon: GitMerge, href: "/reconciliation", keywords: "match invoices" },
      { label: "Documents", group: "Operations", icon: FileText, href: "/documents" },
      { label: "Integrations", group: "Operations", icon: Building2, href: "/integrations", keywords: "connect toast gmail" },
      { label: "Job Monitor", group: "Operations", icon: Activity, href: "/jobs" },
      { label: "Marketing", group: "Marketing", icon: Megaphone, href: "/marketing" },
      { label: "Google Ads", group: "Marketing", icon: Zap, href: "/google-ads", keywords: "spend roas" },
      { label: "Reviews", group: "Marketing", icon: Star, href: "/reviews", keywords: "google rating" },
      { label: "AI Advisor", group: "AI", icon: Bot, href: "/insights", keywords: "insights recommendations" },
      { label: "Settings", group: "Operations", icon: Settings, href: "/settings" },
      {
        label: theme === "dark" ? "Switch to light theme" : "Switch to dark theme",
        group: "Actions",
        icon: theme === "dark" ? Sun : Moon,
        action: () => setTheme(theme === "dark" ? "light" : "dark"),
        keywords: "theme dark light mode",
      },
    ],
    [theme, setTheme]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter(
      (c) =>
        c.label.toLowerCase().includes(q) ||
        c.group.toLowerCase().includes(q) ||
        (c.keywords ?? "").toLowerCase().includes(q)
    );
  }, [query, commands]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  useEffect(() => setActive(0), [query]);

  function run(cmd: Command) {
    setOpen(false);
    if (cmd.href) router.push(cmd.href);
    else cmd.action?.();
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] px-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setOpen(false)} />
      <div
        className="relative w-full max-w-lg rounded-xl border border-border bg-card shadow-2xl overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
      >
        <div className="flex items-center gap-2.5 px-4 border-b border-border">
          <Search className="h-4 w-4 text-muted-foreground shrink-0" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, filtered.length - 1)); }
              else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
              else if (e.key === "Enter" && filtered[active]) { e.preventDefault(); run(filtered[active]); }
            }}
            placeholder="Search pages and actions…"
            className="flex-1 bg-transparent py-3.5 text-sm outline-none placeholder:text-muted-foreground"
          />
          <kbd className="text-[10px] font-medium text-muted-foreground border border-border rounded px-1.5 py-0.5">ESC</kbd>
        </div>
        <div className="max-h-[320px] overflow-y-auto py-1.5">
          {filtered.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-muted-foreground">No results.</p>
          ) : (
            filtered.map((cmd, i) => {
              const Icon = cmd.icon;
              return (
                <button
                  key={cmd.label}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => run(cmd)}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors cursor-pointer ${
                    i === active ? "bg-primary/10 text-primary" : "text-foreground hover:bg-muted/50"
                  }`}
                >
                  <Icon className={`h-4 w-4 shrink-0 ${i === active ? "text-primary" : "text-muted-foreground"}`} />
                  <span className="flex-1">{cmd.label}</span>
                  <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{cmd.group}</span>
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
