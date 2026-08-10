<script lang="ts" module>
  /** What a chip IS, not how it looks — so a row of them can be triaged. */
  export type BadgeKind =
    | "status"    // carries meaning: state, sync warnings. Coloured.
    | "identity"  // names the thing: format, rank, role. Quiet unless the hue is itself the label.
    | "link"      // goes somewhere. Taller, hover affordance.
    | "control";  // does something. Taller, bordered, pressable.

  /** Status tones carry meaning; categorical tones are arbitrary labels (roles, platforms). */
  export type BadgeTone =
    | "neutral" | "info" | "pending" | "danger" | "highlight"
    | "blue" | "amethyst" | "fuchsia" | "crimson" | "slate" | "accent";

  const TONE: Record<BadgeTone, string> = {
    neutral: "bg-surface-muted text-ink-muted",
    info: "badge-info",
    pending: "badge-pending",
    danger: "badge-danger",
    highlight: "badge-highlight",
    blue: "badge-blue",
    amethyst: "badge-amethyst",
    fuchsia: "badge-fuchsia",
    crimson: "badge-crimson",
    slate: "badge-slate",
    accent: "bg-accent-soft/60 text-link-soft",
  };

  /** For the few surfaces that need the tone on something that is not a chip —
   *  the role EDITORS render text-sm toggle buttons, not badges. */
  export function badgeToneClass(tone: BadgeTone): string {
    return TONE[tone];
  }
</script>

<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    kind = "identity",
    tone = "neutral",
    href,
    external = false,
    onclick,
    title,
    truncate = false,
    lapsed = false,
    children,
  }: {
    kind?: BadgeKind;
    tone?: BadgeTone;
    href?: string;
    /** New tab, with the usual rel hardening. */
    external?: boolean;
    onclick?: () => void;
    title?: string;
    /** Cap free text (league names, venues) instead of letting it own the row. */
    truncate?: boolean;
    /** The label no longer applies — lifted, expired, superseded. Still legible. */
    lapsed?: boolean;
    children: Snippet;
  } = $props();

  const interactive = $derived(kind === "link" || kind === "control");
  // Taller when interactive: that is the affordance, not just the touch target.
  const cls = $derived(
    [
      "inline-flex items-center gap-1 rounded text-xs font-medium",
      interactive ? "px-2 py-1 min-h-[32px]" : "px-2 py-0.5",
      TONE[tone],
      truncate ? "max-w-48 truncate" : "",
      lapsed ? "line-through opacity-60" : "",
    ]
      .filter(Boolean)
      .join(" "),
  );
</script>

{#if kind === "link" && href}
  <a
    {href}
    {title}
    target={external ? "_blank" : undefined}
    rel={external ? "noopener noreferrer" : undefined}
    class="{cls} hover:opacity-80 transition-opacity"
  >{@render children()}</a>
{:else if kind === "control"}
  <button
    type="button"
    {onclick}
    {title}
    class="{cls} border border-line hover:bg-surface-hover cursor-pointer transition-colors"
  >{@render children()}</button>
{:else}
  <span {title} class={cls}>{@render children()}</span>
{/if}
