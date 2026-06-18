import { SidebarNav } from "@/components/layout/sidebar-nav";
import { AuthGuard } from "@/components/layout/auth-guard";
import { HistoricalImportBanner } from "@/components/layout/historical-import-banner";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden">
        <SidebarNav />
        <div className="flex-1 flex flex-col overflow-hidden">
          <HistoricalImportBanner />
          <main className="flex-1 overflow-y-auto bg-muted/20 p-6">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}
