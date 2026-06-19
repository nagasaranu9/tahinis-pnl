/**
 * Category Mapping Editor
 * Configure platform + campaign type → expense category mappings
 */
import { useState } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Trash2, Plus } from 'lucide-react';

interface Mapping {
  id: string;
  pipeboard_platform: string;
  pipeboard_campaign_type?: string;
  expense_category: string;
}

interface Props {
  mappings: Mapping[];
  loading?: boolean;
  error?: string;
  onSave: (mapping: Omit<Mapping, 'id'>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}

const PLATFORMS = [
  { value: 'google_ads', label: 'Google Ads' },
  { value: 'meta_ads', label: 'Meta Ads' },
  { value: 'tiktok_ads', label: 'TikTok Ads' },
];

const CAMPAIGN_TYPES = [
  { value: 'SEARCH', label: 'Search' },
  { value: 'DISPLAY', label: 'Display' },
  { value: 'PERFORMANCE_MAX', label: 'Performance Max' },
  { value: 'SHOPPING', label: 'Shopping' },
  { value: 'VIDEO', label: 'Video' },
];

const EXPENSE_CATEGORIES = [
  'Marketing',
  'Brand Awareness',
  'Performance Marketing',
  'Social Media',
  'Digital Advertising',
  'Promotional',
];

export function CategoryMappingEditor({
  mappings,
  loading,
  error,
  onSave,
  onDelete,
}: Props) {
  const [isAdding, setIsAdding] = useState(false);
  const [formData, setFormData] = useState({
    platform: '',
    campaign_type: '',
    category: '',
  });
  const [savingId, setSavingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.platform || !formData.category) return;

    try {
      await onSave({
        pipeboard_platform: formData.platform,
        pipeboard_campaign_type: formData.campaign_type || undefined,
        expense_category: formData.category,
      });
      setFormData({ platform: '', campaign_type: '', category: '' });
      setIsAdding(false);
    } catch (err) {
      console.error('Save failed:', err);
    }
  };

  const handleDelete = async (id: string) => {
    setDeletingId(id);
    try {
      await onDelete(id);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h3 className="text-lg font-semibold text-slate-900 mb-4">Category Mappings</h3>
        <p className="text-sm text-slate-600 mb-6">
          Configure how marketing spend from each platform is categorized in your P&L.
        </p>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-red-800 text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-500 border-t-transparent" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="border-slate-200 hover:bg-transparent">
                  <TableHead className="text-slate-700 font-semibold">Platform</TableHead>
                  <TableHead className="text-slate-700 font-semibold">Campaign Type</TableHead>
                  <TableHead className="text-slate-700 font-semibold">Expense Category</TableHead>
                  <TableHead className="w-12" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {mappings.map((mapping) => (
                  <TableRow key={mapping.id} className="border-slate-100">
                    <TableCell className="font-medium">
                      {PLATFORMS.find((p) => p.value === mapping.pipeboard_platform)?.label}
                    </TableCell>
                    <TableCell className="text-slate-600">
                      {mapping.pipeboard_campaign_type
                        ? CAMPAIGN_TYPES.find((t) => t.value === mapping.pipeboard_campaign_type)?.label
                        : 'Any'}
                    </TableCell>
                    <TableCell className="font-medium text-blue-600">
                      {mapping.expense_category}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(mapping.id)}
                        disabled={deletingId === mapping.id}
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>

      {!isAdding ? (
        <Button
          onClick={() => setIsAdding(true)}
          className="w-full bg-blue-600 hover:bg-blue-700"
        >
          <Plus className="w-4 h-4 mr-2" />
          Add Mapping
        </Button>
      ) : (
        <Card className="p-6 border-blue-200">
          <h4 className="font-semibold text-slate-900 mb-4">New Mapping</h4>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label htmlFor="platform" className="text-slate-700 font-medium">
                Platform
              </Label>
              <Select value={formData.platform} onValueChange={(v) => setFormData({ ...formData, platform: v })}>
                <SelectTrigger id="platform">
                  <SelectValue placeholder="Select platform" />
                </SelectTrigger>
                <SelectContent>
                  {PLATFORMS.map((p) => (
                    <SelectItem key={p.value} value={p.value}>
                      {p.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="campaign-type" className="text-slate-700 font-medium">
                Campaign Type (optional)
              </Label>
              <Select
                value={formData.campaign_type}
                onValueChange={(v) => setFormData({ ...formData, campaign_type: v })}
              >
                <SelectTrigger id="campaign-type">
                  <SelectValue placeholder="Leave empty for all types" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">Any Campaign Type</SelectItem>
                  {CAMPAIGN_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <Label htmlFor="category" className="text-slate-700 font-medium">
                Expense Category
              </Label>
              <Select value={formData.category} onValueChange={(v) => setFormData({ ...formData, category: v })}>
                <SelectTrigger id="category">
                  <SelectValue placeholder="Select category" />
                </SelectTrigger>
                <SelectContent>
                  {EXPENSE_CATEGORIES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="flex gap-2 pt-2">
              <Button
                type="submit"
                disabled={!formData.platform || !formData.category || savingId !== null}
                className="flex-1 bg-blue-600 hover:bg-blue-700"
              >
                {savingId ? 'Saving...' : 'Save Mapping'}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setIsAdding(false);
                  setFormData({ platform: '', campaign_type: '', category: '' });
                }}
                className="flex-1"
              >
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      )}
    </div>
  );
}
