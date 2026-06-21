"use client";

import { useState } from "react";
import { format } from "date-fns";
import { AlertCircle, Bot, CheckCircle, Eraser, Paperclip, Plus, RefreshCw, Trash2, User, X } from "lucide-react";
import { EXPENSE_CATEGORIES } from "@/types/expense";
import {
  useExpenses,
  useOverrideCategory,
  useRecategorize,
  useDeleteExpense,
  useCreateManualExpense,
  usePurgeExpenseRange,
} from "@/hooks/use-expenses";
import { useLocationStore } from "@/lib/location-store";
import type { Expense, ExpenseCategory } from "@/types/expense";

function AddExpenseModal({ onClose }: { onClose: () => void }) {
  const [expenseDate, setExpenseDate] = useState(format(new Date(), "yyyy-MM-dd"));
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("");
  const [receipt, setReceipt] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const locationId = useLocationStore((s) => s.selectedLocationId);
  const { mutate: createExpense, isPending } = useCreateManualExpense();

  const handleSubmit = () => {
    if (!description.trim() || !amount.trim()) {
      setError("Description and amount are required.");
      return;
    }
    if (Number.isNaN(parseFloat(amount))) {
      setError("Amount must be a number.");
      return;
    }
    setError(null);
    createExpense(
      {
        expense_date: expenseDate,
        description: description.trim(),
        amount,
        category: category || undefined,
        location_id: locationId ?? undefined,
        receipt,
      },
      {
        onSuccess: onClose,
        onError: () => setError("Failed to save expense. Try again."),
      }
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-card border border-border rounded-lg shadow-lg w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Add Expense</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        </div>

        {error && (
          <div className="text-sm text-destructive bg-destructive/5 border border-destructive/20 rounded px-3 py-2">
            {error}
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Date</label>
            <input
              type="date"
              value={expenseDate}
              onChange={(e) => setExpenseDate(e.target.value)}
              className="mt-1 w-full text-sm border border-input rounded-md px-3 py-1.5 bg-background"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Description / Vendor</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Sysco Foods delivery"
              className="mt-1 w-full text-sm border border-input rounded-md px-3 py-1.5 bg-background"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Amount (CAD)</label>
            <input
              type="number"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="0.00"
              className="mt-1 w-full text-sm border border-input rounded-md px-3 py-1.5 bg-background"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Category (optional — AI will suggest one if left blank)</label>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="mt-1 w-full text-sm border border-input rounded-md px-3 py-1.5 bg-background"
            >
              <option value="">— Let AI categorize —</option>
              {EXPENSE_CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Receipt (optional — PDF/JPG/PNG, will be OCR'd)</label>
            <label className="mt-1 flex items-center gap-2 w-full text-sm border border-dashed border-input rounded-md px-3 py-2 bg-background cursor-pointer hover:bg-muted/30">
              <Paperclip className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <span className="truncate text-muted-foreground">{receipt ? receipt.name : "Attach receipt…"}</span>
              <input
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.tiff"
                className="hidden"
                onChange={(e) => setReceipt(e.target.files?.[0] ?? null)}
              />
            </label>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="text-sm px-3 py-1.5 rounded-md border border-border hover:bg-muted">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={isPending}
            className="text-sm px-3 py-1.5 rounded-md bg-primary text-primary-foreground disabled:opacity-50"
          >
            {isPending ? "Saving…" : "Save Expense"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ResetMonthModal({ onClose }: { onClose: () => void }) {
  const today = new Date();
  const [start, setStart] = useState(
    format(new Date(today.getFullYear(), today.getMonth() - 1, 1), "yyyy-MM-dd")
  );
  const [end, setEnd] = useState(
    format(new Date(today.getFullYear(), today.getMonth(), 0), "yyyy-MM-dd")
  );
  const locationId = useLocationStore((s) => s.selectedLocationId);
  const { mutate: purge, isPending, data: result } = usePurgeExpenseRange();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-card border border-border rounded-lg shadow-lg w-full max-w-md p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Reset a period (purge expenses)</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-muted">
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="text-sm text-muted-foreground">
          Deletes all auto-extracted expenses in this date range so you can re-upload
          and reprocess the source statements cleanly. Original documents are kept;
          manually-overridden expenses are preserved.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground">From</label>
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="mt-1 w-full text-sm border border-input rounded-md px-3 py-1.5 bg-background"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">To</label>
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="mt-1 w-full text-sm border border-input rounded-md px-3 py-1.5 bg-background"
            />
          </div>
        </div>
        {result && (
          <div className="flex items-center gap-2 text-sm text-green-500">
            <CheckCircle className="h-4 w-4" />
            Purged {result.deleted} expense{result.deleted !== 1 ? "s" : ""}. Now
            re-upload the statements in Documents to reprocess.
          </div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="text-sm px-3 py-1.5 rounded-md border border-border hover:bg-muted">
            Close
          </button>
          <button
            onClick={() => {
              if (
                confirm(
                  `Delete all auto-extracted expenses from ${start} to ${end}? This cannot be undone.`
                )
              ) {
                purge({ start, end, locationId: locationId ?? undefined });
              }
            }}
            disabled={isPending}
            className="text-sm px-3 py-1.5 rounded-md bg-destructive text-destructive-foreground disabled:opacity-50"
          >
            {isPending ? "Purging…" : "Purge range"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ConfidenceBadge({ score }: { score: string | null }) {
  if (!score) return null;
  const pct = Math.round(parseFloat(score) * 100);
  const color = pct >= 80 ? "text-green-400 bg-green-500/10" : pct >= 50 ? "text-yellow-400 bg-yellow-500/10" : "text-red-400 bg-red-500/10";
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${color}`}>{pct}%</span>
  );
}

function CategorySelect({
  expense,
  onSave,
  saving,
}: {
  expense: Expense;
  onSave: (category: string) => void;
  saving: boolean;
}) {
  const [value, setValue] = useState<string>(expense.category ?? "");

  return (
    <div className="flex items-center gap-2">
      <select
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="text-sm border border-input rounded-md px-2 py-1.5 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
      >
        <option value="">— Uncategorized —</option>
        {EXPENSE_CATEGORIES.map((c) => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>
      {value !== (expense.category ?? "") && (
        <button
          onClick={() => onSave(value)}
          disabled={saving || !value}
          className="text-xs px-2 py-1 bg-primary text-primary-foreground rounded disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      )}
    </div>
  );
}

function ExpenseRow({ expense }: { expense: Expense }) {
  const { mutate: overrideCategory, isPending: saving } = useOverrideCategory();
  const { mutate: recategorize, isPending: recategorizing } = useRecategorize();
  const { mutate: deleteExpense, isPending: deleting } = useDeleteExpense();

  return (
    <tr className="border-b border-border hover:bg-muted/30">
      <td className="px-4 py-3 text-sm font-medium">{expense.vendor_name ?? "—"}</td>
      <td className="px-4 py-3 text-sm text-right tabular-nums">
        {expense.amount != null
          ? `${expense.currency_code} ${parseFloat(expense.amount).toFixed(2)}`
          : "—"}
      </td>
      <td className="px-4 py-3">
        <CategorySelect
          expense={expense}
          onSave={(cat) => overrideCategory({ expenseId: expense.id, category: cat })}
          saving={saving}
        />
      </td>
      <td className="px-4 py-3 text-sm">
        {expense.is_ai_categorized ? (
          <div className="flex items-center gap-1.5">
            {expense.user_overridden ? (
              <User className="h-3.5 w-3.5 text-blue-400 shrink-0" />
            ) : (
              <Bot className="h-3.5 w-3.5 text-primary shrink-0" />
            )}
            <span className="text-muted-foreground text-xs truncate max-w-[180px]" title={expense.ai_explanation ?? ""}>
              {expense.ai_suggested_category}
            </span>
            <ConfidenceBadge score={expense.ai_confidence_score} />
          </div>
        ) : (
          <span className="text-xs text-muted-foreground">Not yet analyzed</span>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-muted-foreground">
        {expense.expense_date ? format(new Date(expense.expense_date), "MMM d, yyyy") : "—"}
      </td>
      <td className="px-4 py-3">
        <div className="flex gap-1">
          <button
            onClick={() => recategorize(expense.id)}
            disabled={recategorizing}
            title="Re-run AI categorization"
            className="p-1 rounded hover:bg-muted disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${recategorizing ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={() => {
              if (confirm("Delete this expense?")) deleteExpense(expense.id);
            }}
            disabled={deleting}
            title="Delete"
            className="p-1 rounded hover:bg-destructive/10 text-destructive disabled:opacity-50"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </td>
    </tr>
  );
}

export default function ExpensesPage() {
  const [category, setCategory] = useState("");
  const [vendorSearch, setVendorSearch] = useState("");
  const [uncategorizedOnly, setUncategorizedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showResetModal, setShowResetModal] = useState(false);
  const locationId = useLocationStore((s) => s.selectedLocationId);

  const { data, isLoading, isError } = useExpenses({
    category: category || undefined,
    vendor_name: vendorSearch || undefined,
    uncategorized_only: uncategorizedOnly,
    location_id: locationId ?? undefined,
    page,
    limit: 50,
  });

  const total = data?.meta.total ?? 0;
  const totalPages = Math.ceil(total / 50);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Expenses</h1>
          <p className="text-sm text-muted-foreground mt-1">
            AI-categorized expenses from all connected sources. Override categories manually.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowResetModal(true)}
            title="Purge auto-extracted expenses for a date range, then reprocess"
            className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md border border-destructive/40 text-destructive hover:bg-destructive/10"
          >
            <Eraser className="h-4 w-4" />
            Reset month
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-md bg-primary text-primary-foreground hover:opacity-90"
          >
            <Plus className="h-4 w-4" />
            Add Expense
          </button>
        </div>
      </div>

      {showAddModal && <AddExpenseModal onClose={() => setShowAddModal(false)} />}
      {showResetModal && <ResetMonthModal onClose={() => setShowResetModal(false)} />}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center">
        <input
          type="text"
          placeholder="Search vendor…"
          value={vendorSearch}
          onChange={(e) => { setVendorSearch(e.target.value); setPage(1); }}
          className="text-sm border border-input rounded-md px-3 py-1.5 w-48 bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <select
          value={category}
          onChange={(e) => { setCategory(e.target.value); setPage(1); }}
          className="text-sm border border-input rounded-md px-3 py-1.5 bg-background text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
        >
          <option value="">All categories</option>
          {EXPENSE_CATEGORIES.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={uncategorizedOnly}
            onChange={(e) => { setUncategorizedOnly(e.target.checked); setPage(1); }}
          />
          Uncategorized only
        </label>
        <span className="ml-auto text-sm text-muted-foreground">{total} expense{total !== 1 ? "s" : ""}</span>
      </div>

      {isError && (
        <div className="flex items-center gap-2 text-sm text-destructive bg-destructive/5 border border-destructive/20 rounded px-4 py-2">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Failed to load expenses.
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : data?.data.length === 0 ? (
        <div className="border border-border rounded-lg p-8 text-center text-sm text-muted-foreground bg-card">
          <CheckCircle className="h-8 w-8 mx-auto mb-2 text-muted-foreground/40" />
          No expenses found. Upload documents or connect email to start importing.
        </div>
      ) : (
        <div className="border border-border rounded-lg overflow-x-auto bg-card">
          <table className="w-full text-sm min-w-[640px]">
            <thead className="bg-muted/30 border-b border-border">
              <tr>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Vendor</th>
                <th className="px-4 py-2.5 text-right text-xs font-semibold uppercase tracking-wider text-muted-foreground">Amount</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Category</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">AI Suggestion</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">Date</th>
                <th className="px-4 py-2.5 text-left font-medium w-16"></th>
              </tr>
            </thead>
            <tbody>
              {data?.data.map((expense) => (
                <ExpenseRow key={expense.id} expense={expense} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex justify-center gap-2 text-sm">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1 border border-border rounded-md disabled:opacity-50 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            Previous
          </button>
          <span className="px-3 py-1 text-muted-foreground">
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1 border border-border rounded-md disabled:opacity-50 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
