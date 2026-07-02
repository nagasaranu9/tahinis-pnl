"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useReconciliationFlags } from "@/hooks/use-reconciliation";
import { LayoutDashboard, TrendingUp, Bot, Bell, Menu } from "lucide-react";

const ITEMS = [
  { label: "Home", href: "/dashboard", icon: LayoutDashboard },
  { label: "Reports", href: "/pnl", icon: TrendingUp },
  { label: "AI", href: "/insights", icon: Bot },
  { label: "Alerts", href: "/reconciliation", icon: Bell },
];

/**
 * Mobile-only bottom navigation. Hidden on lg+. "More" dispatches a
 * toggle-sidebar event that SidebarNav listens for to open its drawer.
 */
export function BottomNav() {
  const pathname = usePathname();
  const { data: flags } = useReconciliationFlags({ unresolved_only: true });
  const unresolved = flags?.meta?.total ?? 0;

  return (
    <nav
      className="lg:hidden fixed bottom-0 inset-x-0 z-40 h-16 bg-card/95 backdrop-blur-md border-t border-border/60 flex items-stretch"
      aria-label="Bottom navigation"
    >
      {ITEMS.map((item) => {
        const Icon = item.icon;
        const active = pathname === item.href || pathname.startsWith(item.href + "/");
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "relative flex-1 flex flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors",
              active ? "text-primary" : "text-muted-foreground"
            )}
          >
            <Icon className="h-5 w-5" />
            {item.label}
            {item.href === "/reconciliation" && unresolved > 0 && (
              <span className="absolute top-2.5 right-[calc(50%-18px)] h-2 w-2 rounded-full bg-red-500" />
            )}
          </Link>
        );
      })}
      <button
        onClick={() => window.dispatchEvent(new CustomEvent("toggle-sidebar"))}
        className="flex-1 flex flex-col items-center justify-center gap-0.5 text-[10px] font-medium text-muted-foreground cursor-pointer"
      >
        <Menu className="h-5 w-5" />
        More
      </button>
    </nav>
  );
}
