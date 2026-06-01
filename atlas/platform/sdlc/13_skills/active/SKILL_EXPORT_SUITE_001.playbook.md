# export-suite

<!-- Source: migrated from ~/.claude/skills/export-suite/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: export-suite -->

**Summary.** Complete export capability: PDF generation (jsPDF + html2canvas), Excel workbooks (SheetJS with formatting), CSV download with BOM, PNG/SVG chart snapshots, print CSS, scheduled reports (email/Slack/Teams), and template-based report customization. Trigger on: 'export', 'download report', 'PDF', 'Excel', 'CSV', 'print', 'PNG snapshot', 'scheduled report'.

# Complete Export Suite

## Purpose & Scope

Adds PDF, Excel, CSV, PNG/SVG export and print functionality to any dashboard. Handles formatting, accessibility, branding, and scheduled distribution.

## When to Trigger

- User needs export functionality (PDF, Excel, CSV, PNG)
- User asks for print stylesheets or report generation
- User wants scheduled report distribution (email, Slack, Teams)
- User needs chart snapshot export

## When NOT to Trigger

- Chart configuration → **chart-builder** skill
- Data processing → **data-pipeline** skill
- Deployment → **deploy-pipeline** skill

## PDF Generation (jsPDF + html2canvas)

```javascript
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';

async function exportToPDF(element, filename = 'Transdev_KPI_Report.pdf') {
  const canvas = await html2canvas(element, {
    scale: 2, useCORS: true, logging: false,
    backgroundColor: '#FFFFFF',
  });
  const imgData = canvas.toDataURL('image/png');
  const pdf = new jsPDF('landscape', 'mm', 'a4');
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();

  // Header
  pdf.setFontSize(18);
  pdf.setFont('helvetica', 'bold');
  pdf.text('Transdev KPI Dashboard Report', 14, 20);
  pdf.setFontSize(10);
  pdf.setFont('helvetica', 'normal');
  pdf.text(`Generated: ${new Date().toLocaleDateString()}`, 14, 28);

  // Content
  const imgWidth = pageWidth - 28;
  const imgHeight = (canvas.height * imgWidth) / canvas.width;
  let yOffset = 35;

  if (imgHeight > pageHeight - 45) {
    // Multi-page
    let remainingHeight = imgHeight;
    while (remainingHeight > 0) {
      pdf.addImage(imgData, 'PNG', 14, yOffset, imgWidth, imgHeight);
      remainingHeight -= (pageHeight - yOffset - 10);
      if (remainingHeight > 0) { pdf.addPage(); yOffset = 14; }
    }
  } else {
    pdf.addImage(imgData, 'PNG', 14, yOffset, imgWidth, imgHeight);
  }

  // Footer
  const pageCount = pdf.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    pdf.setPage(i);
    pdf.setFontSize(8);
    pdf.text(`Page ${i} of ${pageCount}`, pageWidth - 30, pageHeight - 10);
    pdf.text('Confidential', 14, pageHeight - 10);
  }

  pdf.save(filename);
}
```

## Excel Export (SheetJS)

```javascript
import * as XLSX from 'xlsx';

function exportToExcel(data, filename = 'Transdev_KPI_Data.xlsx') {
  const wb = XLSX.utils.book_new();

  // Summary Sheet
  const summaryData = [
    ['Transdev KPI Report', '', '', ''],
    ['Generated', new Date().toLocaleDateString()],
    [''],
    ['Metric', 'Current', 'Target', 'Status', 'Penalty'],
    ...data.map(kpi => [kpi.label, kpi.value, kpi.target, kpi.status, kpi.penalty]),
    [''],
    ['Total Penalties', '', '', '', data.reduce((sum, k) => sum + (k.penalty || 0), 0)],
  ];
  const ws = XLSX.utils.aoa_to_sheet(summaryData);

  // Column widths
  ws['!cols'] = [{ wch: 25 }, { wch: 12 }, { wch: 12 }, { wch: 15 }, { wch: 12 }];

  // Bold header row
  ['A4', 'B4', 'C4', 'D4', 'E4'].forEach(cell => {
    if (ws[cell]) ws[cell].s = { font: { bold: true } };
  });

  XLSX.utils.book_append_sheet(wb, ws, 'Summary');
  XLSX.writeFile(wb, filename);
}
```

## CSV Export

```javascript
function exportToCSV(data, columns, filename = 'kpi_data.csv') {
  const BOM = '\uFEFF'; // Excel UTF-8 compatibility
  const headers = columns.map(c => c.header).join(',');
  const rows = data.map(row =>
    columns.map(col => {
      const val = row[col.id];
      if (val == null) return '';
      const str = String(val);
      return str.includes(',') || str.includes('"') || str.includes('\n')
        ? `"${str.replace(/"/g, '""')}"` : str;
    }).join(',')
  );
  const csv = BOM + [headers, ...rows].join('\r\n');
  downloadBlob(csv, filename, 'text/csv;charset=utf-8');
}

function downloadBlob(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}
```

## PNG/SVG Chart Snapshots

```javascript
async function exportChartToPNG(chartElement, filename, scale = 2) {
  const canvas = await html2canvas(chartElement, { scale, backgroundColor: '#FFFFFF' });
  canvas.toBlob(blob => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  }, 'image/png');
}

function exportChartToSVG(svgElement, filename) {
  const serializer = new XMLSerializer();
  const svgString = serializer.serializeToString(svgElement);
  const blob = new Blob([svgString], { type: 'image/svg+xml' });
  downloadBlob(blob, filename, 'image/svg+xml');
}
```

## Print CSS

```css
@media print {
  body { font-size: 10pt; color: #000; background: #FFF; }
  .no-print, nav, .sidebar, .export-buttons { display: none !important; }
  .kpi-grid { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .kpi-card { border: 1px solid #CCC; page-break-inside: avoid; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #CCC; padding: 4px 8px; }
  @page { margin: 1.5cm; size: landscape; }
  @page :first { margin-top: 2cm; }
  .page-break { page-break-before: always; }
  h1::after { content: ' — Printed ' attr(data-date); font-size: 10pt; font-weight: normal; }
}
```

## React Export Menu

```tsx
function ExportMenu({ dashboardRef, data, columns }) {
  const [exporting, setExporting] = useState(false);
  const handleExport = async (format) => {
    setExporting(true);
    try {
      switch (format) {
        case 'pdf': await exportToPDF(dashboardRef.current); break;
        case 'excel': exportToExcel(data); break;
        case 'csv': exportToCSV(data, columns); break;
        case 'png': await exportChartToPNG(dashboardRef.current, 'dashboard.png'); break;
        case 'print': window.print(); break;
      }
    } finally { setExporting(false); }
  };
  return (
    <div role="group" aria-label="Export options">
      {['pdf', 'excel', 'csv', 'png', 'print'].map(fmt => (
        <button key={fmt} onClick={() => handleExport(fmt)} disabled={exporting}
          aria-busy={exporting}>{fmt.toUpperCase()}</button>
      ))}
    </div>
  );
}
```

## Filename Conventions

```
Transdev_KPI_[Scope]_[Date].[ext]
Examples:
  Transdev_KPI_July2025_20250731.pdf
  Transdev_KPI_Monthly_20250731.xlsx
  Transdev_KPI_Penalties_20250731.csv
```

## Integration

| Agent | Relationship |
|-------|-------------|
| **COURIER** (Export) | Full export orchestration with scheduling |
| **chart-builder** | Chart snapshot methods |
| **theme-engine** | Brand colors for PDF headers |
| **table-master** | Table data for CSV/Excel export |

## Anti-Patterns

1. **No progress indicator** — large exports need visual feedback
2. **Memory leaks** — always `URL.revokeObjectURL()` after download
3. **Missing BOM in CSV** — Excel needs BOM for UTF-8 detection
4. **No error handling** — wrap exports in try/catch with user notification
5. **Hardcoded filenames** — use conventions with date stamps
