# table-master

<!-- Source: migrated from ~/.claude/skills/table-master/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: table-master -->

**Summary.** Advanced data table patterns: TanStack Table v8, Fluent UI DetailsList, AG Grid. Sorting, filtering, pagination, virtual scrolling for 100K+ rows, column resizing, row selection, cell editing, export integration, sticky headers, responsive design, and ARIA grid accessibility. Trigger on: 'data table', 'DetailsList', 'TanStack Table', 'sortable table', 'filterable table', 'virtual scroll table', 'AG Grid'.

# Advanced Data Table Patterns

## Purpose & Scope

Builds advanced data tables with sorting, filtering, pagination, virtual scrolling, column management, and export integration. Supports TanStack Table v8, Fluent UI DetailsList, AG Grid, and vanilla HTML.

## When to Trigger

- User needs data tables with sorting, filtering, or pagination
- User needs virtual scrolling for large datasets (1000+ rows)
- User asks for TanStack Table, DetailsList, or AG Grid patterns
- User needs month-over-month comparison tables

## When NOT to Trigger

- Chart visualizations → **chart-builder** skill
- KPI card components → **kpi-card-factory** skill
- Data processing → **data-pipeline** skill

## Column Definition Patterns

```typescript
type ColumnType = 'text' | 'number' | 'currency' | 'percentage' | 'date' | 'status' | 'actions' | 'sparkline';

interface ColumnDef {
  id: string;
  header: string;
  type: ColumnType;
  sortable?: boolean;
  filterable?: boolean;
  width?: number;
  sticky?: 'left' | 'right';
  formatter?: (value: any) => string;
}

const KPI_COLUMNS: ColumnDef[] = [
  { id: 'month', header: 'Month', type: 'date', sticky: 'left', sortable: true },
  { id: 'pph', header: 'PPH', type: 'number', sortable: true,
    formatter: v => v.toFixed(2) },
  { id: 'otp', header: 'OTP %', type: 'percentage', sortable: true },
  { id: 'lateTrips', header: 'Late Trips %', type: 'percentage', sortable: true },
  { id: 'penalty', header: 'Penalty', type: 'currency', sortable: true,
    formatter: v => `$${v.toLocaleString()}` },
  { id: 'status', header: 'Status', type: 'status' },
  { id: 'trend', header: 'Trend', type: 'sparkline', sortable: false },
];
```

## TanStack Table v8 (React)

```tsx
import { useReactTable, getCoreRowModel, getSortedRowModel, getFilteredRowModel,
  getPaginationRowModel, flexRender, type ColumnDef } from '@tanstack/react-table';

function KpiTable({ data }: { data: IKpiData[] }) {
  const [sorting, setSorting] = useState([]);
  const [globalFilter, setGlobalFilter] = useState('');

  const columns: ColumnDef<IKpiData>[] = [
    { accessorKey: 'reportMonth', header: 'Month',
      cell: info => new Date(info.getValue()).toLocaleDateString('en-US', { month: 'short', year: 'numeric' }) },
    { accessorKey: 'pph', header: 'PPH',
      cell: info => info.getValue().toFixed(2) },
    { accessorKey: 'otp', header: 'OTP',
      cell: info => `${info.getValue().toFixed(1)}%` },
    { accessorKey: 'lateTripsPercent', header: 'Late Trips',
      cell: info => {
        const val = info.getValue();
        return <span className={val > 5 ? 'text-red-600 font-bold' : 'text-green-600'}>{val.toFixed(1)}%</span>;
      }},
    { accessorKey: 'totalPenalty', header: 'Penalty',
      cell: info => `$${info.getValue().toLocaleString()}` },
  ];

  const table = useReactTable({
    data, columns, state: { sorting, globalFilter },
    onSortingChange: setSorting, onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(), getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(), getPaginationRowModel: getPaginationRowModel(),
  });

  return (
    <div>
      <input value={globalFilter} onChange={e => setGlobalFilter(e.target.value)}
        placeholder="Search..." className="mb-4 px-3 py-2 border rounded" />
      <table role="grid" aria-label="KPI Historical Data">
        <thead>
          {table.getHeaderGroups().map(hg => (
            <tr key={hg.id}>
              {hg.headers.map(h => (
                <th key={h.id} onClick={h.column.getToggleSortingHandler()}
                  className="cursor-pointer select-none px-4 py-2 text-left"
                  aria-sort={h.column.getIsSorted() === 'asc' ? 'ascending' : h.column.getIsSorted() === 'desc' ? 'descending' : 'none'}>
                  {flexRender(h.column.columnDef.header, h.getContext())}
                  {{ asc: ' ↑', desc: ' ↓' }[h.column.getIsSorted()] ?? ''}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map(row => (
            <tr key={row.id} className="border-b hover:bg-gray-50">
              {row.getVisibleCells().map(cell => (
                <td key={cell.id} className="px-4 py-2">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex justify-between mt-4">
        <span>Page {table.getState().pagination.pageIndex + 1} of {table.getPageCount()}</span>
        <div>
          <button onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>Previous</button>
          <button onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>Next</button>
        </div>
      </div>
    </div>
  );
}
```

## Virtual Scrolling (100K+ Rows)

```tsx
import { useVirtualizer } from '@tanstack/react-virtual';

function VirtualTable({ data, columns }) {
  const parentRef = useRef(null);
  const rowVirtualizer = useVirtualizer({
    count: data.length, getScrollElement: () => parentRef.current,
    estimateSize: () => 40, overscan: 20,
  });

  return (
    <div ref={parentRef} style={{ height: '600px', overflow: 'auto' }}>
      <div style={{ height: `${rowVirtualizer.getTotalSize()}px`, position: 'relative' }}>
        {rowVirtualizer.getVirtualItems().map(virtualRow => (
          <div key={virtualRow.index}
            style={{ position: 'absolute', top: virtualRow.start, height: virtualRow.size, width: '100%' }}>
            <TableRow data={data[virtualRow.index]} columns={columns} />
          </div>
        ))}
      </div>
    </div>
  );
}
```

## Sticky Headers & Columns

```css
.table-container { overflow: auto; max-height: 600px; }
.table-container thead th { position: sticky; top: 0; z-index: 2; background: var(--color-surface); }
.table-container td:first-child,
.table-container th:first-child { position: sticky; left: 0; z-index: 1; background: var(--color-surface); }
```

## MoM Comparison with Color-Coded Deltas

```tsx
function DeltaCell({ current, previous }: { current: number; previous: number }) {
  const delta = current - previous;
  const pct = previous !== 0 ? (delta / previous) * 100 : 0;
  const color = delta > 0 ? 'text-green-600' : delta < 0 ? 'text-red-600' : 'text-gray-500';
  return (
    <span className={color}>
      {delta > 0 ? '+' : ''}{delta.toFixed(1)} ({pct > 0 ? '+' : ''}{pct.toFixed(1)}%)
    </span>
  );
}
```

## Export Integration

```javascript
function exportTableToCSV(data, columns, filename) {
  const BOM = '\uFEFF';
  const headers = columns.map(c => c.header).join(',');
  const rows = data.map(row => columns.map(c => {
    const val = row[c.id];
    return typeof val === 'string' && val.includes(',') ? `"${val}"` : val;
  }).join(','));
  const csv = BOM + [headers, ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}
```

## Accessibility

- `role="grid"` on table element with `aria-label`
- `aria-sort` on sortable column headers (ascending/descending/none)
- Arrow key navigation between cells
- Enter to activate sort or edit
- Escape to cancel editing
- Screen reader announces sort changes via `aria-live`

## Responsive

```css
@media (max-width: 768px) {
  .table-responsive { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .table-responsive td { white-space: nowrap; }
}
```

## Integration

| Agent | Relationship |
|-------|-------------|
| **All framework agents** | Framework-specific table implementations |
| **export-suite** | CSV/Excel export from table data |
| **TURBO** | Virtual scrolling performance |
| **BEACON** | ARIA grid accessibility compliance |

## Anti-Patterns

1. **No virtual scrolling for large datasets** — paginate or virtualize at 100+ rows
2. **Missing ARIA attributes** — tables need role="grid" and aria-sort
3. **No sticky headers** — users lose column context when scrolling
4. **Client-side sort on server-paginated data** — sort on server for paginated datasets
5. **Hardcoded column widths** — use flexible widths with min-width constraints
