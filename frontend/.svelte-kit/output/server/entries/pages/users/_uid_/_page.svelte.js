import { a0 as store_get, a3 as head, a2 as unsubscribe_stores } from "../../../../chunks/index2.js";
import { p as page } from "../../../../chunks/stores.js";
import "idb";
import { I as Icon } from "../../../../chunks/Icon.js";
import { e as escape_html } from "../../../../chunks/context.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    var $$store_subs;
    store_get($$store_subs ??= {}, "$page", page).params.uid;
    head("zgdid4", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>${escape_html("User")} - Archon</title>`);
      });
    });
    $$renderer2.push(`<div class="max-w-3xl mx-auto px-4 py-6">`);
    {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div class="text-center text-ash-400 py-8">`);
      Icon($$renderer2, {
        icon: "lucide:loader-2",
        class: "w-6 h-6 animate-spin inline-block"
      });
      $$renderer2.push(`<!----> <span class="ml-2">Loading...</span></div>`);
    }
    $$renderer2.push(`<!--]--></div>`);
    if ($$store_subs) unsubscribe_stores($$store_subs);
  });
}
export {
  _page as default
};
//# sourceMappingURL=_page.svelte.js.map
