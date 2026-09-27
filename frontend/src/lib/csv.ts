/** Quote fields containing comma, quote, CR or LF; double embedded quotes. */
export function buildCsv(rows: string[][]): string {
  const esc = (f: string) => (/[",\r\n]/.test(f) ? `"${f.replaceAll('"', '""')}"` : f);
  return rows.map((r) => r.map(esc).join(',')).join('\r\n') + '\r\n';
}
