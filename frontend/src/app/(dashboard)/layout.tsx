import { SidebarNav } from "@/components/layout/sidebar-nav";
import { BottomNav } from "@/components/layout/bottom-nav";
import { CommandPalette } from "@/components/layout/command-palette";
import { AuthGuard } from "@/components/layout/auth-guard";
import { HistoricalImportBanner } from "@/components/layout/historical-import-banner";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden">
        <SidebarNav />
        <div className="flex-1 flex flex-col overflow-hidden pt-12 lg:pt-0">
          <HistoricalImportBanner />
          <main className="flex-1 overflow-y-auto bg-muted/20 p-3 sm:p-4 lg:p-6 pb-20 lg:pb-6">
            {children}
          </main>
        </div>
      </div>
      <BottomNav />
      <CommandPalette />
    </AuthGuard>
  );
}
