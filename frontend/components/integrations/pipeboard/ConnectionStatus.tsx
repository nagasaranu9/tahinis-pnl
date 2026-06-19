/**
 * Pipeboard Connection Status Card
 * Shows connected/disconnected state, last sync time, sync indicator
 */
import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { AlertCircle, CheckCircle2, Clock, LogOut, Link2 } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';

interface ConnectionProps {
  connected: boolean;
  lastSyncAt?: string;
  lastSyncError?: string;
  isActive: boolean;
  accountId?: string;
  onReconnect: () => void;
  onDisconnect: () => void;
  syncInProgress?: boolean;
}

export function ConnectionStatus({
  connected,
  lastSyncAt,
  lastSyncError,
  isActive,
  accountId,
  onReconnect,
  onDisconnect,
  syncInProgress,
}: ConnectionProps) {
  const [disconnectLoading, setDisconnectLoading] = useState(false);

  const handleDisconnect = async () => {
    setDisconnectLoading(true);
    try {
      await onDisconnect();
    } finally {
      setDisconnectLoading(false);
    }
  };

  const lastSyncDate = lastSyncAt ? new Date(lastSyncAt) : null;

  return (
    <Card className={`p-6 ${!connected || !isActive ? 'border-amber-200 bg-amber-50' : 'border-green-200 bg-green-50'}`}>
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          {connected && isActive ? (
            <CheckCircle2 className="w-8 h-8 text-green-600 flex-shrink-0 mt-0.5" />
          ) : (
            <AlertCircle className="w-8 h-8 text-amber-600 flex-shrink-0 mt-0.5" />
          )}

          <div className="min-w-0 flex-1">
            <h3 className={`text-lg font-semibold ${connected && isActive ? 'text-green-900' : 'text-amber-900'}`}>
              {connected && isActive ? 'Connected to Pipeboard' : 'Not Connected'}
            </h3>

            {connected && isActive && lastSyncDate && (
              <div className="mt-2 flex items-center gap-2 text-sm text-green-700">
                <Clock className="w-4 h-4" />
                <span>Last sync {formatDistanceToNow(lastSyncDate, { addSuffix: true })}</span>
              </div>
            )}

            {syncInProgress && (
              <div className="mt-2 flex items-center gap-2 text-sm text-blue-700">
                <div className="animate-spin rounded-full h-4 w-4 border-2 border-blue-500 border-t-transparent" />
                <span>Sync in progress...</span>
              </div>
            )}

            {!isActive && lastSyncError && (
              <div className="mt-2 text-sm text-amber-700 font-medium">
                {lastSyncError}
              </div>
            )}

            {accountId && (
              <div className="mt-3 text-xs text-slate-600 font-mono bg-white/50 px-2 py-1 rounded">
                Account: {accountId.substring(0, 8)}...
              </div>
            )}
          </div>
        </div>

        <div className="flex gap-2 flex-shrink-0">
          {!connected || !isActive ? (
            <Button
              onClick={onReconnect}
              size="sm"
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              <Link2 className="w-4 h-4 mr-2" />
              Reconnect
            </Button>
          ) : (
            <Button
              onClick={handleDisconnect}
              variant="outline"
              size="sm"
              disabled={disconnectLoading}
              className="text-red-600 hover:text-red-700 hover:bg-red-50"
            >
              <LogOut className="w-4 h-4 mr-2" />
              {disconnectLoading ? 'Disconnecting...' : 'Disconnect'}
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
