import { a3 as head } from "../../../../../chunks/index2.js";
import "@sveltejs/kit/internal";
import "../../../../../chunks/exports.js";
import "../../../../../chunks/utils.js";
import { e as escape_html } from "../../../../../chunks/context.js";
import "clsx";
import "@sveltejs/kit/internal/server";
import "../../../../../chunks/state.svelte.js";
import { I as Icon } from "../../../../../chunks/Icon.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    head("1fyvj4c", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>${escape_html("Reset Password")} - Archon</title>`);
      });
    });
    $$renderer2.push(`<div class="min-h-screen flex items-center justify-center p-4"><div class="w-full max-w-md"><div class="text-center mb-8"><h1 class="text-4xl font-light text-crimson-500 mb-2">Archon</h1> <p class="text-ash-400">VEKN Tournament Management</p></div> <div class="bg-dusk-950 rounded-lg shadow-lg p-8 border border-ash-800">`);
    {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div class="space-y-4 text-center"><div class="w-16 h-16 mx-auto flex items-center justify-center">`);
      Icon($$renderer2, {
        icon: "lucide:loader-2",
        class: "w-10 h-10 animate-spin text-crimson-500"
      });
      $$renderer2.push(`<!----></div> <h2 class="text-lg font-medium text-bone-100">Verifying link...</h2> <p class="text-ash-400 text-sm">Please wait</p></div>`);
    }
    $$renderer2.push(`<!--]--></div></div></div>`);
  });
}
export {
  _page as default
};
//# sourceMappingURL=_page.svelte.js.map
