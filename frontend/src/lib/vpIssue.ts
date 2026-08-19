import * as m from "$lib/paraglide/messages.js";
import type { VpIssue } from "$lib/engine";

/** Shared by the rounds and finals scoring views so both name the same cause the same way.
 * `incomplete` is deliberately absent: it means "still being typed in", which the table's own In Progress state already says. */
export function vpIssueText(issue: VpIssue, tableSize: number): string {
  switch (issue.code) {
    case "impossible_oust_order":
      return m.vp_blocked_oust_order({ seat: (issue.seats[0] ?? 0) + 1 });
    case "half_vp_mismatch":
      return m.vp_blocked_half_vp({
        seats: issue.seats.map((s) => s + 1).join(", "),
      });
    case "excessive_total":
      return m.vp_blocked_excessive({ max: tableSize });
    case "redirected_vp":
      return m.vp_blocked_redirected();
    case "invalid_table_size":
      return m.vp_blocked_table_size({ size: tableSize });
    default:
      return m.vp_blocked_generic();
  }
}
