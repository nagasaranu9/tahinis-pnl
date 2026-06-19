/**
 * Campaign Performance Table
 * Shows campaigns with spend, impressions, clicks, conversions, ROAS
 * Supports row click drill-down to campaign details
 */
import { useState } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ChevronRight, TrendingUp } from 'lucide-react';

interface Campaign {
  id: string;
  name: string;
  platform: string;
  status: 'ENABLED' | 'PAUSED' | 'ARCHIVED';
  spend: number;
  impressions: number;
  clicks: number;
  conversions?: number;
  roas?: number;
}

interface Props {
  campaigns: Campaign[];
  loading?: boolean;
  error?: string;
  onRowClick?: (campaign: Campaign) => void;
}

const statusColors = {
  ENABLED: 'bg-green-100 text-green-800',
  PAUSED: 'bg-yellow-100 text-yellow-800',
  ARCHIVED: 'bg-gray-100 text-gray-800',
};

const platformColors = {
  google_ads: 'bg-blue-100 text-blue-800',
  meta_ads: 'bg-blue-200 text-blue-900',
  tiktok_ads: 'bg-amber-100 text-amber-800',
};

export function CampaignTable({ campaigns, loading, error, onRowClick }: Props) {
  const [sortBy, setSortBy] = useState<'spend' | 'roas' | 'impressions'>('spend');

  if (loading) {
    return (
      <Card className="p-6">
        <div className="flex items-center justify-center h-80">
          <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-500 border-t-transparent" />
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="p-6 border-red-200 bg-red-50">
        <p className="text-red-800 text-sm">{error}</p>
      </Card>
    );
  }

  if (!campaigns || campaigns.length === 0) {
    return (
      <Card className="p-6">
        <div className="text-center py-12">
          <p className="text-slate-500">No campaigns found</p>
        </div>
      </Card>
    );
  }

  const sorted = [...campaigns].sort((a, b) => {
    const aVal = a[sortBy] ?? 0;
    const bVal = b[sortBy] ?? 0;
    return (bVal as number) - (aVal as number);
  });

  return (
    <Card className="p-6">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-lg font-semibold text-slate-900">Campaign Performance</h3>
        <div className="flex gap-2">
          {(['spend', 'roas', 'impressions'] as const).map((key) => (
            <Button
              key={key}
              variant={sortBy === key ? 'default' : 'outline'}
              size="sm"
              onClick={() => setSortBy(key)}
              className="text-xs"
            >
              {key === 'roas' ? 'ROAS' : key.charAt(0).toUpperCase() + key.slice(1)}
            </Button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="border-slate-200 hover:bg-transparent">
              <TableHead className="text-slate-700 font-semibold">Campaign</TableHead>
              <TableHead className="text-slate-700 font-semibold">Platform</TableHead>
              <TableHead className="text-slate-700 font-semibold">Status</TableHead>
              <TableHead className="text-right text-slate-700 font-semibold">Spend</TableHead>
              <TableHead className="text-right text-slate-700 font-semibold">Impressions</TableHead>
              <TableHead className="text-right text-slate-700 font-semibold">Clicks</TableHead>
              <TableHead className="text-right text-slate-700 font-semibold">CTR</TableHead>
              <TableHead className="text-right text-slate-700 font-semibold">Conv.</TableHead>
              <TableHead className="text-right text-slate-700 font-semibold">ROAS</TableHead>
              <TableHead className="w-8" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((campaign) => {
              const ctr = campaign.impressions > 0
                ? ((campaign.clicks / campaign.impressions) * 100).toFixed(2)
                : '0.00';

              return (
                <TableRow
                  key={campaign.id}
                  className="border-slate-100 hover:bg-slate-50 cursor-pointer transition-colors"
                  onClick={() => onRowClick?.(campaign)}
                >
                  <TableCell className="font-medium text-slate-900">{campaign.name}</TableCell>
                  <TableCell>
                    <Badge
                      className={`${platformColors[campaign.platform as keyof typeof platformColors] || 'bg-gray-100 text-gray-800'} font-medium`}
                    >
                      {campaign.platform.replace(/_/g, ' ')}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge
                      className={`${statusColors[campaign.status]} font-medium`}
                      variant="outline"
                    >
                      {campaign.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    ${campaign.spend.toLocaleString('en-US', { maximumFractionDigits: 2 })}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {campaign.impressions.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {campaign.clicks.toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-slate-600">
                    {ctr}%
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {campaign.conversions !== undefined
                      ? campaign.conversions.toLocaleString('en-US', { maximumFractionDigits: 1 })
                      : '—'}
                  </TableCell>
                  <TableCell className="text-right">
                    {campaign.roas !== undefined ? (
                      <span className="flex items-center justify-end gap-1 tabular-nums font-semibold text-green-700">
                        <TrendingUp className="w-4 h-4" />
                        {campaign.roas.toFixed(2)}x
                      </span>
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}
