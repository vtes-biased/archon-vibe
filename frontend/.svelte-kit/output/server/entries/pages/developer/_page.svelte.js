import { a3 as head } from "../../../chunks/index2.js";
import "@sveltejs/kit/internal";
import "../../../chunks/exports.js";
import "../../../chunks/utils.js";
import "clsx";
import "@sveltejs/kit/internal/server";
import "../../../chunks/state.svelte.js";
import "idb";
import { I as Icon } from "../../../chunks/Icon.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    head("d1wr8x", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>Developer Portal - Archon</title>`);
      });
    });
    $$renderer2.push(`<div class="max-w-3xl mx-auto p-4"><div class="flex items-center justify-between mb-6"><div><h1 class="text-2xl font-light text-bone-100">Developer Portal</h1> <p class="text-ash-400 text-sm">Manage your OAuth applications</p></div> <button class="px-4 py-2 bg-crimson-700 hover:bg-crimson-600 text-bone-100 rounded-lg text-sm font-medium transition-colors flex items-center gap-2">`);
    Icon($$renderer2, { icon: "lucide:plus", class: "w-4 h-4" });
    $$renderer2.push(`<!----> Register App</button></div> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div class="flex items-center justify-center py-12">`);
      Icon($$renderer2, {
        icon: "lucide:loader-2",
        class: "w-8 h-8 animate-spin text-ash-400"
      });
      $$renderer2.push(`<!----></div>`);
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--></div>`);
  });
}
export {
  _page as default
};
//# sourceMappingURL=_page.svelte.js.map
