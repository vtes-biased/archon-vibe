<script lang="ts">
  import { apiRequest } from "$lib/api";
  import { toUserMessage } from "$lib/errors";
  import Button from "$lib/components/Button.svelte";
  import { Upload, X, TriangleAlert, CircleCheck } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';
  import { dialogPanel } from "$lib/actions/dialog";

  let {
    show = $bindable(),
    tournamentUid,
    onImported,
  }: {
    show: boolean;
    tournamentUid: string;
    onImported?: () => void;
  } = $props();

  interface Row { vekn_id?: string; email?: string; name?: string; paid?: boolean }
  interface ImportResult {
    registered: string[];
    already_registered: string[];
    unmatched: { row: number; name: string; reason: string }[];
    failed: { name: string; reason: string }[];
  }

  let rows = $state<Row[]>([]);
  let parseError = $state<string | null>(null);
  let fileName = $state("");
  let defaultPaid = $state(true);
  let loading = $state(false);
  let result = $state<ImportResult | null>(null);
  let error = $state<string | null>(null);

  // Minimal RFC4180 parser: quoted fields, embedded commas/newlines, CRLF.
  function parseCsv(text: string): string[][] {
    const out: string[][] = [];
    let field = "", record: string[] = [], inQuotes = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (inQuotes) {
        if (c === '"') {
          if (text[i + 1] === '"') { field += '"'; i++; }
          else inQuotes = false;
        } else field += c;
      } else if (c === '"') inQuotes = true;
      else if (c === ",") { record.push(field); field = ""; }
      else if (c === "\n" || c === "\r") {
        if (c === "\r" && text[i + 1] === "\n") i++;
        record.push(field); field = "";
        if (record.some(f => f.trim() !== "")) out.push(record);
        record = [];
      } else field += c;
    }
    record.push(field);
    if (record.some(f => f.trim() !== "")) out.push(record);
    return out;
  }

  const HEADER_ALIASES: Record<"email" | "name" | "paid", string[]> = {
    email: ["email", "e-mail", "mail"],
    name: ["name", "player", "player name", "attendee"],
    paid: ["paid", "payment", "payment status"],
  };

  function handleFile(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    fileName = file.name;
    parseError = null;
    rows = [];
    result = null;
    const reader = new FileReader();
    reader.onload = () => {
      const records = parseCsv(String(reader.result ?? ""));
      if (records.length < 2) {
        parseError = m.csv_import_empty();
        return;
      }
      const header = (records[0] ?? []).map(h => h.trim().toLowerCase());
      const colOf = (key: keyof typeof HEADER_ALIASES) =>
        header.findIndex(h => HEADER_ALIASES[key].includes(h));
      const cols = {
        vekn_id: header.findIndex(h => h.includes("vekn")),
        email: colOf("email"),
        name: colOf("name"),
        paid: colOf("paid"),
      };
      if (cols.vekn_id < 0 && cols.email < 0) {
        parseError = m.csv_import_no_id_column();
        return;
      }
      const cell = (r: string[], idx: number): string =>
        idx >= 0 ? (r[idx] ?? "").trim() : "";
      rows = records.slice(1).map(r => {
        const row: Row = {};
        const vekn = cell(r, cols.vekn_id);
        const email = cell(r, cols.email);
        const name = cell(r, cols.name);
        const paid = cell(r, cols.paid);
        if (vekn) row.vekn_id = vekn;
        if (email) row.email = email;
        if (name) row.name = name;
        if (paid) row.paid = ["1", "true", "yes", "paid", "y"].includes(paid.toLowerCase());
        return row;
      }).filter(r => r.vekn_id || r.email);
      if (rows.length === 0) parseError = m.csv_import_empty();
    };
    reader.readAsText(file);
  }

  async function doImport() {
    loading = true;
    error = null;
    try {
      result = await apiRequest<ImportResult>(`/api/tournaments/${tournamentUid}/bulk-register`, {
        method: "POST",
        body: JSON.stringify({ rows, default_paid: defaultPaid }),
      });
      onImported?.();
    } catch (e) {
      error = toUserMessage(e, m.csv_import_error());
    } finally {
      loading = false;
    }
  }

  function close() {
    show = false;
    rows = [];
    result = null;
    parseError = null;
    error = null;
    fileName = "";
  }

  function unmatchedReason(reason: string): string {
    if (reason === "no_vekn_id") return m.csv_import_reason_no_vekn();
    if (reason === "duplicate_row") return m.csv_import_reason_duplicate();
    return m.csv_import_reason_not_found();
  }
</script>

{#if show}
  <div
    role="presentation"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
    onclick={(e) => { e.stopPropagation(); if (e.target === e.currentTarget) close(); }}
  >
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="csv-import-title"
      tabindex="-1"
      use:dialogPanel={close}
      class="bg-surface-card rounded-lg shadow-xl border border-line w-full max-w-lg mx-4 max-h-[85dvh] overflow-y-auto"
    >
      <div class="p-6 border-b border-line flex items-center justify-between">
        <h2 id="csv-import-title" class="text-xl font-medium text-ink-strong">{m.csv_import_title()}</h2>
        <button onclick={close} class="min-w-[44px] min-h-[44px] -m-2 inline-flex items-center justify-center text-ink-faint hover:text-ink-strong" title={m.common_cancel()}>
          <X class="w-4 h-4" />
        </button>
      </div>
      <div class="p-6 space-y-4">
        {#if result}
          <p class="text-sm text-info inline-flex items-center gap-1.5">
            <CircleCheck class="w-4 h-4 shrink-0" aria-hidden="true" />
            {m.csv_import_done({ registered: String(result.registered.length), already: String(result.already_registered.length) })}
          </p>
          {#if result.unmatched.length > 0}
            <div class="banner-warn border rounded-lg p-3 text-sm">
              <p class="font-medium mb-1">{m.csv_import_unmatched({ count: String(result.unmatched.length) })}</p>
              <ul class="list-disc list-inside space-y-0.5 text-xs">
                {#each result.unmatched as u}
                  <li>{u.name} — {unmatchedReason(u.reason)}</li>
                {/each}
              </ul>
              <p class="mt-2 text-xs">{m.csv_import_unmatched_hint()}</p>
            </div>
          {/if}
          {#if result.failed.length > 0}
            <div class="banner-warn border rounded-lg p-3 text-sm">
              <p class="font-medium mb-1">{m.csv_import_failed({ count: String(result.failed.length) })}</p>
              <ul class="list-disc list-inside space-y-0.5 text-xs">
                {#each result.failed as f}
                  <li>{f.name} — {f.reason}</li>
                {/each}
              </ul>
            </div>
          {/if}
          <Button variant="secondary" size="lg" onclick={close}>{m.common_close()}</Button>
        {:else}
          <p class="text-sm text-ink-muted">{m.csv_import_desc()}</p>
          <p class="text-xs text-ink-faint">{m.csv_import_columns()}</p>
          <input
            type="file"
            accept=".csv,text/csv"
            onchange={handleFile}
            class="block w-full text-sm text-ink file:mr-3 file:px-3 file:py-2 file:rounded-lg file:border file:border-line-strong file:bg-surface-hover file:text-ink-bright file:text-sm"
          />
          {#if parseError}
            <p class="text-sm text-warn inline-flex items-center gap-1.5">
              <TriangleAlert class="w-4 h-4 shrink-0" aria-hidden="true" />
              {parseError}
            </p>
          {/if}
          {#if rows.length > 0}
            <p class="text-sm text-ink">{m.csv_import_preview({ count: String(rows.length), file: fileName })}</p>
            <label class="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" bind:checked={defaultPaid}
                class="w-5 h-5 rounded border-line-strong bg-surface-card text-accent focus:ring-accent" />
              <span class="text-sm text-ink-bright">{m.csv_import_default_paid()}</span>
            </label>
          {/if}
          {#if error}
            <p class="text-sm text-link">{error}</p>
          {/if}
          <div class="flex gap-2">
            <Button variant="primary" size="lg" class="flex-1" loading={loading} disabled={rows.length === 0 || loading} onclick={doImport}>
              <Upload class="w-4 h-4" aria-hidden="true" />
              {m.csv_import_submit({ count: String(rows.length) })}
            </Button>
            <Button variant="secondary" size="lg" disabled={loading} onclick={close}>{m.common_cancel()}</Button>
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}
