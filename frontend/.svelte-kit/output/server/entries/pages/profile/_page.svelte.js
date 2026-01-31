import { a3 as head } from "../../../chunks/index2.js";
import "@sveltejs/kit/internal";
import "../../../chunks/exports.js";
import "../../../chunks/utils.js";
import "clsx";
import "@sveltejs/kit/internal/server";
import "../../../chunks/state.svelte.js";
import { g as getAuthState } from "../../../chunks/auth.svelte.js";
import "idb";
import { g as getCountries } from "../../../chunks/geonames.js";
import "../../../chunks/functions.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    const auth = getAuthState();
    const countries = getCountries();
    Object.values(countries).sort((a, b) => a.name.localeCompare(b.name));
    auth.authMethods.find((m) => m.type === "discord")?.identifier || null;
    let $$settled = true;
    let $$inner_renderer;
    function $$render_inner($$renderer3) {
      head("maq4gq", $$renderer3, ($$renderer4) => {
        $$renderer4.title(($$renderer5) => {
          $$renderer5.push(`<title>Profile - Archon</title>`);
        });
      });
      $$renderer3.push(`<div class="p-4 sm:p-8"><div class="max-w-2xl mx-auto"><h1 class="text-3xl font-light text-crimson-500 mb-6">Profile</h1> `);
      {
        $$renderer3.push("<!--[-->");
        $$renderer3.push(`<div class="bg-dusk-950 rounded-lg shadow p-8 border border-ash-800 text-center"><div class="text-ash-400">Loading...</div></div>`);
      }
      $$renderer3.push(`<!--]--></div></div> `);
      {
        $$renderer3.push("<!--[!-->");
      }
      $$renderer3.push(`<!--]--> `);
      {
        $$renderer3.push("<!--[!-->");
      }
      $$renderer3.push(`<!--]--> `);
      {
        $$renderer3.push("<!--[!-->");
      }
      $$renderer3.push(`<!--]-->`);
    }
    do {
      $$settled = true;
      $$inner_renderer = $$renderer2.copy();
      $$render_inner($$inner_renderer);
    } while (!$$settled);
    $$renderer2.subsume($$inner_renderer);
  });
}
export {
  _page as default
};
//# sourceMappingURL=_page.svelte.js.map
