"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useAuthStore } from "@/lib/auth-store";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { Role } from "@/types/auth";
import { useReconciliationFlags } from "@/hooks/use-reconciliation";
import {
  LayoutDashboard,
  FileText,
  DollarSign,
  GitMerge,
  TrendingUp,
  Bot,
  Settings,
  LogOut,
  Building2,
  Megaphone,
  Activity,
  LayoutGrid,
  Moon,
  Sun,
} from "lucide-react";
import { useEffect, useState } from "react";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  roles: Role[];
}

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard, roles: ["owner", "manager", "viewer"] },
  { label: "P&L Reports", href: "/pnl", icon: TrendingUp, roles: ["owner", "manager", "viewer"] },
  { label: "Documents", href: "/documents", icon: FileText, roles: ["owner", "manager", "viewer"] },
  { label: "Expenses", href: "/expenses", icon: DollarSign, roles: ["owner", "manager", "viewer"] },
  { label: "Reconciliation", href: "/reconciliation", icon: GitMerge, roles: ["owner", "manager", "viewer"] },
  { label: "AI Insights", href: "/insights", icon: Bot, roles: ["owner", "manager", "viewer"] },
  { label: "Marketing", href: "/marketing", icon: Megaphone, roles: ["owner", "manager", "viewer"] },
  { label: "Job Monitor", href: "/jobs", icon: Activity, roles: ["owner", "manager"] },
  { label: "Integrations", href: "/integrations", icon: Building2, roles: ["owner"] },
  { label: "Settings", href: "/settings", icon: Settings, roles: ["owner"] },
];

export function SidebarNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const { getRole, getLocationId, clearTokens, refreshToken } = useAuthStore();
  const [mounted, setMounted] = useState(false);

  const role = getRole();
  const isAdmin = getLocationId() === null;

  useEffect(() => {
    setMounted(true);
  }, []);

  const { data: flags } = useReconciliationFlags({ unresolved_only: true });
  const unresolvedCount = flags?.meta?.total ?? 0;

  const visibleItems = NAV_ITEMS.filter((item) =>
    role ? item.roles.includes(role) : false
  );

  async function handleLogout() {
    if (refreshToken) {
      try {
        await apiClient.post("/api/v1/auth/logout", { refresh_token: refreshToken });
      } catch {
        // best-effort
      }
    }
    clearTokens();
    router.replace("/login");
  }

  const toggleTheme = () => {
    setTheme(theme === "dark" ? "light" : "dark");
  };

  return (
    <aside className="w-60 flex flex-col bg-card h-full shrink-0 border-r border-border/60">
      {/* Logo header — centered, no text */}
      <div className="py-6 px-4 flex flex-col items-center gap-3 border-b border-border/60">
        <Link href="/dashboard" className="cursor-pointer flex items-center justify-center w-12 h-12 rounded-lg bg-muted hover:bg-muted/80 transition-colors">
          <svg width="28" height="28" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M50 15C35 15 25 25 25 40C25 50 30 55 35 60C32 65 28 75 28 85L72 85C72 75 68 65 65 60C70 55 75 50 75 40C75 25 65 15 50 15Z" fill="currentColor" className="text-red-600" />
            <circle cx="50" cy="30" r="4" fill="white" />
          </svg>
        </Link>

        {/* Location info */}
        {getLocationId() && (
          <div className="text-center text-xs space-y-1">
            <div className="text-[11px] text-muted-foreground/70">Location #{getLocationId()}</div>
          </div>
        )}
      </div>

      {/* Theme toggle */}
      <div className="px-4 py-2 border-b border-border/60">
        <button
          onClick={toggleTheme}
          className="w-full flex items-center justify-center gap-2 py-1.5 px-3 rounded-md text-[12px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
          aria-label="Toggle theme"
        >
          {mounted && (
            <>
              {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              <span>{theme === "dark" ? "Light" : "Dark"}</span>
            </>
          )}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-2.5 py-3 space-y-px overflow-y-auto" aria-label="Primary">
        {isAdmin && (
          <>
            <Link
              href="/locations"
              className={cn(
                "relative flex items-center gap-3 pl-3.5 pr-2.5 py-[7px] rounded-md text-[13.5px] font-medium transition-colors duration-150 cursor-pointer mb-1",
                pathname === "/locations"
                  ? "bg-primary/8 text-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
              )}
            >
              {pathname === "/locations" && (
                <span className="absolute left-0 top-1.5 bottom-1.5 w-[2.5px] rounded-full bg-primary" />
              )}
              <LayoutGrid className={cn("h-[17px] w-[17px] shrink-0", pathname === "/locations" ? "text-primary" : "text-muted-foreground/80")} />
              <span className="flex-1 truncate">All Locations</span>
            </Link>
            <div className="h-px bg-border/60 mx-1 mb-1" />
          </>
        )}
        {visibleItems.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "relative flex items-center gap-3 pl-3.5 pr-2.5 py-[7px] rounded-md text-[13.5px] font-medium transition-colors duration-150 cursor-pointer",
                active
                  ? "bg-primary/8 text-primary"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
              )}
            >
              {active && (
                <span className="absolute left-0 top-1.5 bottom-1.5 w-[2.5px] rounded-full bg-primary" />
              )}
              <Icon className={cn("h-[17px] w-[17px] shrink-0", active ? "text-primary" : "text-muted-foreground/80")} />
              <span className="flex-1 truncate">{item.label}</span>
              {item.href === "/reconciliation" && unresolvedCount > 0 && (
                <span className="ml-auto text-[10px] font-semibold bg-red-500/12 text-red-500 px-1.5 py-0.5 rounded-full min-w-[18px] text-center leading-tight tabular-nums">
                  {unresolvedCount > 99 ? "99+" : unresolvedCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-2.5 py-2.5 border-t border-border/60">
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 pl-3.5 pr-2.5 py-[7px] w-full rounded-md text-[13.5px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors duration-150 cursor-pointer"
        >
          <LogOut className="h-[17px] w-[17px] shrink-0 text-muted-foreground/80" />
          Sign out
        </button>
      </div>
    </aside>
  );
}
