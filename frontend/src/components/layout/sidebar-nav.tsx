"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useAuthStore } from "@/lib/auth-store";
import { apiClient } from "@/lib/api-client";
import { cn } from "@/lib/utils";
import type { Role } from "@/types/auth";
import { useReconciliationFlags } from "@/hooks/use-reconciliation";
import { useLocations } from "@/hooks/use-locations";
import { useToastStatus } from "@/hooks/use-toast-integration";
import { LocationSelector } from "@/components/layout/location-selector";
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
  Menu,
  X,
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

function formatRelative(iso: string | null): string {
  if (!iso) return "Never synced";
  const then = new Date(iso).getTime();
  const diffSec = Math.floor((Date.now() - then) / 1000);
  if (diffSec < 60) return "Synced just now";
  if (diffSec < 3600) return `Synced ${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `Synced ${Math.floor(diffSec / 3600)}h ago`;
  return `Synced ${Math.floor(diffSec / 86400)}d ago`;
}

export function SidebarNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const { getRole, getLocationId, clearTokens, refreshToken } = useAuthStore();
  const [mounted, setMounted] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const role = getRole();
  const isAdmin = getLocationId() === null;

  const { locations, selectedLocationId } = useLocations();
  const selectedLocation = locations.find((l) => l.id === selectedLocationId);
  const { data: toastStatus } = useToastStatus(selectedLocationId ?? undefined);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Close the mobile drawer whenever the route changes.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

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
    <>
      {/* Mobile top bar with hamburger (hidden on lg+) */}
      <div className="lg:hidden fixed top-0 inset-x-0 z-50 h-12 flex items-center gap-2 px-3 bg-card border-b border-border/60">
        <button
          onClick={() => setMobileOpen(true)}
          className="p-1.5 -ml-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
          aria-label="Open menu"
        >
          <Menu className="h-5 w-5" />
        </button>
        <img src="/tahinis-icon.png" alt="Tahini's" className="w-7 h-7 object-contain" />
        <div className="min-w-0 flex-1">
          <LocationSelector />
        </div>
      </div>
      {/* Backdrop when drawer open */}
      {mobileOpen && (
        <div
          className="lg:hidden fixed inset-0 z-50 bg-black/50"
          onClick={() => setMobileOpen(false)}
          aria-hidden
        />
      )}

      <aside
        className={cn(
          "w-60 flex flex-col bg-card h-full shrink-0 border-r border-border/60",
          "fixed inset-y-0 left-0 z-50 transition-transform duration-200 lg:static lg:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Close button (mobile only) */}
        <button
          onClick={() => setMobileOpen(false)}
          className="lg:hidden absolute top-3 right-3 p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors cursor-pointer"
          aria-label="Close menu"
        >
          <X className="h-4 w-4" />
        </button>
      {/* Logo header — centered, no text */}
      <div className="py-6 px-4 flex flex-col items-center gap-3 border-b border-border/60">
        <Link href="/dashboard" className="cursor-pointer flex items-center justify-center w-14 h-14">
          <img
            src="/tahinis-icon.png"
            alt="Tahini's"
            width={56}
            height={56}
            className="w-14 h-14 object-contain"
          />
        </Link>

        {/* Location switcher */}
        <div className="flex flex-col items-center gap-1 text-xs">
          <LocationSelector />
          {selectedLocation && toastStatus && (
            <div className="text-[10.5px] text-muted-foreground/70">
              {formatRelative(toastStatus.last_synced_at)}
            </div>
          )}
        </div>
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
                <span className="ml-auto text-[10px] font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400 px-1.5 py-0.5 rounded-full min-w-[18px] text-center leading-tight tabular-nums">
                  {unresolvedCount > 99 ? "99+" : unresolvedCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-2.5 py-2.5 border-t border-border/60 space-y-1">
        {role && (
          <div className="flex items-center gap-2.5 px-2 py-1.5">
            <div className="h-7 w-7 rounded-full bg-primary/12 flex items-center justify-center shrink-0">
              <span className="text-[11px] font-semibold text-primary uppercase">{role.slice(0, 1)}</span>
            </div>
            <div className="min-w-0">
              <div className="text-[12.5px] font-medium text-foreground capitalize truncate">{role}</div>
              <div className="text-[10.5px] text-muted-foreground">Signed in</div>
            </div>
          </div>
        )}
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 pl-3.5 pr-2.5 py-[7px] w-full rounded-md text-[13.5px] font-medium text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors duration-150 cursor-pointer"
        >
          <LogOut className="h-[17px] w-[17px] shrink-0 text-muted-foreground/80" />
          Sign out
        </button>
      </div>
    </aside>
    </>
  );
}
