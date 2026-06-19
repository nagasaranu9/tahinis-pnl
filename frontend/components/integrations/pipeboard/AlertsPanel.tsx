/**
 * Alerts Panel
 * Display active alerts with severity badges and dismiss functionality
 */
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { AlertCircle, AlertTriangle, Info, X } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface Alert {
  id: string;
  severity: 'info' | 'warning' | 'error' | 'critical';
  title: string;
  message: string;
  created_at: string;
}

interface Props {
  alerts: Alert[];
  loading?: boolean;
  onDismiss: (id: string) => Promise<void>;
}

const severityConfig = {
  info: {
    icon: Info,
    bgColor: 'bg-blue-50 border-blue-200',
    textColor: 'text-blue-900',
    badgeColor: 'bg-blue-100 text-blue-800',
  },
  warning: {
    icon: AlertTriangle,
    bgColor: 'bg-yellow-50 border-yellow-200',
    textColor: 'text-yellow-900',
    badgeColor: 'bg-yellow-100 text-yellow-800',
  },
  error: {
    icon: AlertCircle,
    bgColor: 'bg-red-50 border-red-200',
    textColor: 'text-red-900',
    badgeColor: 'bg-red-100 text-red-800',
  },
  critical: {
    icon: AlertCircle,
    bgColor: 'bg-red-50 border-red-300',
    textColor: 'text-red-900',
    badgeColor: 'bg-red-200 text-red-900',
  },
};

export function AlertsPanel({ alerts, loading, onDismiss }: Props) {
  if (loading) {
    return (
      <Card className="p-6">
        <div className="flex items-center justify-center h-20">
          <div className="animate-spin rounded-full h-6 w-6 border-2 border-blue-500 border-t-transparent" />
        </div>
      </Card>
    );
  }

  if (!alerts || alerts.length === 0) {
    return (
      <Card className="p-6 border-green-200 bg-green-50">
        <div className="flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-green-600" />
          <p className="text-green-800 font-medium">All clear! No active alerts.</p>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {alerts.map((alert) => {
        const config = severityConfig[alert.severity];
        const Icon = config.icon;
        const dismissing = false; // Add loading state if needed

        return (
          <Card key={alert.id} className={`p-4 border-2 ${config.bgColor}`}>
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3 flex-1 min-w-0">
                <Icon className={`w-5 h-5 flex-shrink-0 mt-0.5`} style={{ color: config.badgeColor.split(' ')[0].replace('bg-', '#') }} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h4 className={`font-semibold ${config.textColor}`}>{alert.title}</h4>
                    <span className={`px-2 py-1 rounded text-xs font-medium whitespace-nowrap ${config.badgeColor}`}>
                      {alert.severity.toUpperCase()}
                    </span>
                  </div>
                  <p className={`text-sm mt-1 ${config.textColor} opacity-90`}>
                    {alert.message}
                  </p>
                  <p className="text-xs text-slate-500 mt-2">
                    {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}
                  </p>
                </div>
              </div>

              <Button
                variant="ghost"
                size="sm"
                onClick={() => onDismiss(alert.id)}
                disabled={dismissing}
                className={`flex-shrink-0 ${config.textColor} hover:opacity-75`}
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
