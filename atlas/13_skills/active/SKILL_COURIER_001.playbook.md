# courier

<!-- Source: migrated from ~/.claude/skills/courier/SKILL.md on 2026-05-26 -->
<!-- Runtime alias: courier -->

**Summary.** Data export systems for dashboards: PDF generation using jsPDF and html2canvas, Excel export with SheetJS/xlsx, CSV download, ApexCharts dataURI chart snapshots, and print stylesheets. Covers filename conventions, multi-sheet Excel reports, and exporting KPI data with formatting. Trigger on: "PDF export", "Excel download", "export", "print layout", "report generation", "jsPDF", "SheetJS".

# Dashboard Export Systems

## Core Expertise
- PDF generation: jsPDF + html2canvas for full dashboard capture; jsPDF text mode for tabular reports
- Excel export: SheetJS (xlsx) with cell formatting, multiple sheets, column widths
- CSV generation: client-side Blob download without server dependency
- ApexCharts dataURI: embed chart PNG snapshots directly into PDF exports
- Print CSS: media queries to hide navigation, optimize layout for paper
- Filename conventions: `Transdev_KPI_[Scope]_[YYYY-MM].pdf`

## When to Use
- User wants to download, print, or share dashboard data as PDF, Excel, or CSV
- Monthly KPI report needs to be exported with charts and penalty summary
- Excel export required with multiple tabs (Summary, Details, Historical)
- Dashboard needs a print-friendly view

## Key Patterns

1. **PDF Export with jsPDF + html2canvas**
```javascript
import jsPDF from 'jspdf';
import html2canvas from 'html2canvas';

async function exportDashboardPDF(elementId, filename) {
  const el = document.getElementById(elementId);
  const canvas = await html2canvas(el, { scale: 2, useCORS: true });
  const imgData = canvas.toDataURL('image/png');
  const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' });
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = (canvas.height * pageWidth) / canvas.width;
  pdf.addImage(imgData, 'PNG', 0, 0, pageWidth, pageHeight);
  pdf.save(filename || `Transdev_KPI_Dashboard_${formatDateForFilename()}.pdf`);
}
```

2. **Text-Based PDF (Tabular KPI Report)**
```javascript
function exportKPIReportPDF(kpis, month) {
  const pdf = new jsPDF();
  pdf.setFont('helvetica', 'bold');
  pdf.setFontSize(16);
  pdf.text(`Transdev KPI Report — ${month}`, 14, 20);
  pdf.setFontSize(10); pdf.setFont('helvetica', 'normal');
  const rows = kpis.map(k => [k.label, k.value, k.target, k.status, `$${k.penalty.toLocaleString()}`]);
  pdf.autoTable({ head: [['KPI', 'Value', 'Target', 'Status', 'Penalty']], body: rows, startY: 30 });
  pdf.save(`Transdev_KPI_${month.replace(' ', '_')}.pdf`);
}
```

3. **Excel Export with SheetJS (Multi-Sheet)**
```javascript
import * as XLSX from 'xlsx';

function exportKPIExcel(kpis, history, filename) {
  const wb = XLSX.utils.book_new();
  // Sheet 1: Summary
  const summaryData = kpis.map(k => ({
    'KPI': k.label, 'Value': k.value, 'Target': k.target,
    'Status': k.status, 'Penalty ($)': k.penalty,
  }));
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(summaryData), 'Summary');
  // Sheet 2: Historical
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(history), 'Historical');
  XLSX.writeFile(wb, filename || `Transdev_KPI_${formatDateForFilename()}.xlsx`);
}
```

4. **CSV Download (No Library)**
```javascript
function exportCSV(data, filename) {
  const headers = Object.keys(data[0]);
  const rows = data.map(row => headers.map(h => JSON.stringify(row[h] ?? '')).join(','));
  const csv = [headers.join(','), ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement('a'), { href: url, download: filename });
  a.click(); URL.revokeObjectURL(url);
}
```

5. **ApexCharts Snapshot in PDF**
```javascript
async function addChartToPDF(pdf, chartRef, x, y, width, height) {
  const dataUri = await chartRef.current.chart.dataURI();
  pdf.addImage(dataUri.imgURI, 'PNG', x, y, width, height);
}
```

6. **Print CSS**
```css
@media print {
  .no-print, nav, .alert-banner, .export-buttons { display: none !important; }
  .kpi-grid { grid-template-columns: repeat(3, 1fr); }
  .page-break { page-break-before: always; }
  body { font-size: 11px; color: #000; background: #fff; }
  .status-chip { border: 1px solid currentColor; }
}
```

## Standards
- Filename convention: `Transdev_KPI_[Scope]_[YYYY-MM].[ext]` (e.g., `Transdev_KPI_Monthly_2025-07.pdf`)
- Scale html2canvas at 2x for retina-quality PDF images
- Always include report month/year as header text in PDF exports
- Excel currency columns must use number format, not string: `{ t: 'n', z: '$#,##0' }`
- Revoke object URLs immediately after programmatic click to prevent memory leaks
- PDF exports should include generation timestamp in footer
