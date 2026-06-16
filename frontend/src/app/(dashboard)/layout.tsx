import { SidebarNav } from "@/components/layout/sidebar-nav";
import { AuthGuard } from "@/components/layout/auth-guard";
import { LocationSelector } from "@/components/layout/location-selector";
import { ThemeToggle } from "@/components/layout/theme-toggle";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden">
        <SidebarNav />
        <div className="flex-1 flex flex-col overflow-hidden">
          <header className="h-12 flex items-center justify-end gap-2 px-6 border-b border-border bg-card/50 shrink-0">
            <LocationSelector />
            <ThemeToggle />
          </header>
          <main className="flex-1 overflow-y-auto bg-muted/20 p-6">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}
