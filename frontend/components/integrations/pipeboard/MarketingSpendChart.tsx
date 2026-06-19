/**
 * Marketing Spend Breakdown Chart
 * Pie chart showing ad spend by platform (Google, Meta, TikTok) with drill-down to campaigns
 */
import { useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

interface SpendByPlatform {
  platform: string;
  spend: number;
  percentage: number;
  campaigns: number;
}

interface Props {
  data: SpendByPlatform[];
  loading?: boolean;
  error?: string;
}

const COLORS = {
  google_ads: '#1E40AF', // blue-900
  meta_ads: '#3B82F6',    // blue-500
  tiktok_ads: '#F59E0B',  // amber-500
};

const RADIAN = Math.PI / 180;

const renderCustomizedLabel = ({
  cx,
  cy,
  midAngle,
  innerRadius,
  outerRadius,
  percent,
}: any) => {
  const radius = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);

  if (percent < 0.05) return null;

  return (
    <text
      x={x}
      y={y}
      fill="white"
      textAnchor={x > cx ? 'start' : 'end'}
      dominantBaseline="central"
      className="text-xs font-semibold"
    >
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
};

export function MarketingSpendChart({ data, loading, error }: Props) {
  const [selectedPlatform, setSelectedPlatform] = useState<string | null>(null);

  if (loading) {
    return (
      <Card className="p-6">
        <div className="h-80 flex items-center justify-center">
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

  if (!data || data.length === 0) {
    return (
      <Card className="p-6">
        <div className="h-80 flex items-center justify-center">
          <p className="text-slate-500">No marketing spend data available</p>
        </div>
      </Card>
    );
  }

  const total = data.reduce((sum, item) => sum + item.spend, 0);

  return (
    <Card className="p-6">
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-slate-900">Marketing Spend by Platform</h3>
        <p className="text-sm text-slate-600 mt-1">
          Total: ${total.toLocaleString('en-US', { maximumFractionDigits: 2 })}
        </p>
      </div>

      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={renderCustomizedLabel}
            outerRadius={100}
            fill="#8884d8"
            dataKey="spend"
            onClick={(_, index) => setSelectedPlatform(data[index].platform)}
          >
            {data.map((entry) => (
              <Cell
                key={`cell-${entry.platform}`}
                fill={COLORS[entry.platform as keyof typeof COLORS] || '#94A3B8'}
                opacity={!selectedPlatform || selectedPlatform === entry.platform ? 1 : 0.4}
              />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: any) => `$${value.toLocaleString('en-US', { maximumFractionDigits: 2 })}`}
            contentStyle={{ borderRadius: '8px', border: '1px solid #E2E8F0' }}
          />
          <Legend />
        </PieChart>
      </ResponsiveContainer>

      <div className="mt-6 grid grid-cols-3 gap-4">
        {data.map((item) => (
          <div
            key={item.platform}
            className={`p-3 rounded-lg border-2 transition-colors cursor-pointer ${
              selectedPlatform === item.platform
                ? 'border-blue-500 bg-blue-50'
                : 'border-slate-200 hover:border-slate-300'
            }`}
            onClick={() => setSelectedPlatform(item.platform)}
          >
            <div className="text-xs font-medium text-slate-600 uppercase">
              {item.platform.replace(/_/g, ' ')}
            </div>
            <div className="text-lg font-bold text-slate-900 mt-1">
              ${item.spend.toLocaleString('en-US', { maximumFractionDigits: 2 })}
            </div>
            <div className="text-xs text-slate-500 mt-1">{item.campaigns} campaigns</div>
          </div>
        ))}
      </div>
    </Card>
  );
}
