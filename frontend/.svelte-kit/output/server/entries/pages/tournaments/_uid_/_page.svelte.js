import { a0 as store_get, a2 as unsubscribe_stores, a3 as head } from "../../../../chunks/index2.js";
import { p as page } from "../../../../chunks/stores.js";
import "@sveltejs/kit/internal";
import "../../../../chunks/exports.js";
import "../../../../chunks/utils.js";
import { e as escape_html } from "../../../../chunks/context.js";
import "clsx";
import "@sveltejs/kit/internal/server";
import "../../../../chunks/state.svelte.js";
import "idb";
import { I as Icon } from "../../../../chunks/Icon.js";
import "marked";
import "dompurify";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    var $$store_subs;
    store_get($$store_subs ??= {}, "$page", page).params.uid;
    function computeStandings() {
      return [];
    }
    const standings = computeStandings();
    (() => {
      if (!standings.length) return [];
      return [];
    })();
    Intl.DateTimeFormat().resolvedOptions().timeZone;
    let $$settled = true;
    let $$inner_renderer;
    function $$render_inner($$renderer3) {
      head("m0tru0", $$renderer3, ($$renderer4) => {
        $$renderer4.title(($$renderer5) => {
          $$renderer5.push(`<title>${escape_html("Tournament")} - Archon</title>`);
        });
      });
      $$renderer3.push(`<div class="p-4 sm:p-8"><div class="max-w-4xl mx-auto"><a href="/tournaments" class="inline-flex items-center gap-2 text-ash-400 hover:text-ash-200 mb-4">`);
      Icon($$renderer3, { icon: "lucide:arrow-left", class: "w-4 h-4" });
      $$renderer3.push(`<!----> Tournaments</a> `);
      {
        $$renderer3.push("<!--[-->");
        $$renderer3.push(`<div class="text-center py-12">`);
        Icon($$renderer3, {
          icon: "lucide:loader-2",
          class: "mx-auto h-12 w-12 text-ash-500 animate-spin"
        });
        $$renderer3.push(`<!----></div>`);
      }
      $$renderer3.push(`<!--]--></div></div>`);
    }
    do {
      $$settled = true;
      $$inner_renderer = $$renderer2.copy();
      $$render_inner($$inner_renderer);
    } while (!$$settled);
    $$renderer2.subsume($$inner_renderer);
    if ($$store_subs) unsubscribe_stores($$store_subs);
  });
}
export {
  _page as default
};
//# sourceMappingURL=_page.svelte.js.map
