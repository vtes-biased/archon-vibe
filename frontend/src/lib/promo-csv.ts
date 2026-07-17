// Minimal RFC-4180 CSV builder + client-side download. No dependency.

/** Quote fields containing comma, quote, CR or LF; double embedded quotes. */
export function buildCsv(rows: string[][]): string {
  const esc = (f: string) => (/[",\r\n]/.test(f) ? `"${f.replaceAll('"', '""')}"` : f);
  return rows.map((r) => r.map(esc).join(',')).join('\r\n') + '\r\n';
}

/** Trigger a browser download of `csv` as `filename`. */
export function downloadCsv(csv: string, filename: string): void {
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
