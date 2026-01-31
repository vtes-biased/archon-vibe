import { a1 as attr, Z as ensure_array_like, a4 as bind_props, a3 as head } from "../../../../chunks/index2.js";
import "@sveltejs/kit/internal";
import "../../../../chunks/exports.js";
import "../../../../chunks/utils.js";
import "@sveltejs/kit/internal/server";
import "../../../../chunks/state.svelte.js";
import "idb";
import { h as hasAnyRole } from "../../../../chunks/auth.svelte.js";
import { g as getCountries, a as getCountryFlag } from "../../../../chunks/geonames.js";
import { e as escape_html } from "../../../../chunks/context.js";
import { I as Icon } from "../../../../chunks/Icon.js";
function TournamentFields($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let {
      values = void 0,
      onchange,
      disabled = false,
      disabledFields = /* @__PURE__ */ new Set(),
      idPrefix = ""
    } = $$props;
    const countries = getCountries();
    const timezones = Intl.supportedValuesOf("timeZone");
    function id(name) {
      return idPrefix ? `${idPrefix}-${name}` : name;
    }
    function handleInput(field, value) {
      values[field] = value;
      onchange?.(field, value);
    }
    $$renderer2.push(`<div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("name"))}>Name *</label> <input${attr("id", id("name"))} type="text"${attr("value", values.name)}${attr("disabled", disabled, true)} class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none" placeholder="Tournament name"/></div> <div class="grid grid-cols-1 sm:grid-cols-2 gap-4"><div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("format"))}>Format</label> `);
    $$renderer2.select(
      {
        id: id("format"),
        value: values.format,
        disabled,
        onchange: (e) => handleInput("format", e.target.value),
        class: "w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
      },
      ($$renderer3) => {
        $$renderer3.option({ value: "Standard" }, ($$renderer4) => {
          $$renderer4.push(`Standard`);
        });
        $$renderer3.option({ value: "V5" }, ($$renderer4) => {
          $$renderer4.push(`V5`);
        });
        $$renderer3.option({ value: "Limited" }, ($$renderer4) => {
          $$renderer4.push(`Limited`);
        });
      }
    );
    $$renderer2.push(`</div> <div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("rank"))}>Rank</label> `);
    $$renderer2.select(
      {
        id: id("rank"),
        value: values.rank,
        disabled,
        onchange: (e) => handleInput("rank", e.target.value),
        class: "w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
      },
      ($$renderer3) => {
        $$renderer3.option({ value: "" }, ($$renderer4) => {
          $$renderer4.push(`Basic`);
        });
        $$renderer3.option({ value: "National Championship" }, ($$renderer4) => {
          $$renderer4.push(`National Championship`);
        });
        $$renderer3.option({ value: "Continental Championship" }, ($$renderer4) => {
          $$renderer4.push(`Continental Championship`);
        });
      }
    );
    $$renderer2.push(`</div></div> <div><label class="flex items-center gap-3 cursor-pointer"><input type="checkbox"${attr("checked", values.open_rounds, true)}${attr("disabled", disabled || disabledFields.has("open_rounds"), true)} class="w-5 h-5 rounded border-ash-700 bg-dusk-950 text-emerald-600 focus:ring-emerald-500"/> <span class="text-sm text-ash-200">Open Rounds</span></label> <p class="text-xs text-ash-500 mt-1 ml-8">Players participate in up to a maximum number of rounds among all scheduled rounds.</p> `);
    if (values.open_rounds) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div class="mt-2 ml-8"><label class="block text-sm text-ash-400 mb-1"${attr("for", id("max-rounds"))}>Max Rounds</label> `);
      $$renderer2.select(
        {
          id: id("max-rounds"),
          value: String(values.max_rounds),
          disabled: disabled || disabledFields.has("max_rounds"),
          onchange: (e) => handleInput("max_rounds", parseInt(e.target.value)),
          class: "w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
        },
        ($$renderer3) => {
          $$renderer3.option({ value: "0" }, ($$renderer4) => {
            $$renderer4.push(`No limit`);
          });
          $$renderer3.option({ value: "1" }, ($$renderer4) => {
            $$renderer4.push(`1`);
          });
          $$renderer3.option({ value: "2" }, ($$renderer4) => {
            $$renderer4.push(`2`);
          });
          $$renderer3.option({ value: "3" }, ($$renderer4) => {
            $$renderer4.push(`3`);
          });
          $$renderer3.option({ value: "4" }, ($$renderer4) => {
            $$renderer4.push(`4`);
          });
          $$renderer3.option({ value: "5" }, ($$renderer4) => {
            $$renderer4.push(`5`);
          });
        }
      );
      $$renderer2.push(`</div>`);
    } else {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--></div> <div class="grid grid-cols-1 sm:grid-cols-3 gap-4"><div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("start"))}>Start</label> <input${attr("id", id("start"))} type="datetime-local"${attr("value", values.start)}${attr("disabled", disabled, true)} class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"/></div> <div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("finish"))}>Finish</label> <input${attr("id", id("finish"))} type="datetime-local"${attr("value", values.finish)}${attr("disabled", disabled, true)} class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none"/></div> <div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("timezone"))}>Timezone</label> `);
    $$renderer2.select(
      {
        id: id("timezone"),
        value: values.timezone,
        disabled,
        onchange: (e) => handleInput("timezone", e.target.value),
        class: "w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
      },
      ($$renderer3) => {
        $$renderer3.push(`<!--[-->`);
        const each_array = ensure_array_like(timezones);
        for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
          let tz = each_array[$$index];
          $$renderer3.option({ value: tz }, ($$renderer4) => {
            $$renderer4.push(`${escape_html(tz.replace(/_/g, " "))}`);
          });
        }
        $$renderer3.push(`<!--]-->`);
      }
    );
    $$renderer2.push(`</div></div> <label class="flex items-center gap-3 cursor-pointer"><input type="checkbox"${attr("checked", values.online, true)}${attr("disabled", disabled, true)} class="w-5 h-5 rounded border-ash-700 bg-dusk-950 text-emerald-600 focus:ring-emerald-500"/> <span class="text-sm text-ash-200">Online Tournament</span></label> `);
    if (!values.online) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("country"))}>Country</label> `);
      $$renderer2.select(
        {
          id: id("country"),
          value: values.country,
          disabled,
          onchange: (e) => handleInput("country", e.target.value),
          class: "w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
        },
        ($$renderer3) => {
          $$renderer3.option({ value: "" }, ($$renderer4) => {
            $$renderer4.push(`Select country`);
          });
          $$renderer3.push(`<!--[-->`);
          const each_array_1 = ensure_array_like(Object.entries(countries));
          for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
            let [code, c] = each_array_1[$$index_1];
            $$renderer3.option({ value: code }, ($$renderer4) => {
              $$renderer4.push(`${escape_html(c.name)} ${escape_html(getCountryFlag(code))}`);
            });
          }
          $$renderer3.push(`<!--]-->`);
        }
      );
      $$renderer2.push(`</div>`);
    } else {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> <div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("venue"))}>Venue</label> <input${attr("id", id("venue"))} type="text"${attr("value", values.venue)}${attr("disabled", disabled, true)} class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none" placeholder="Venue name"/></div> <div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("venue-url"))}>Venue URL</label> <input${attr("id", id("venue-url"))} type="url"${attr("value", values.venue_url)}${attr("disabled", disabled, true)} class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none" placeholder="https://..."/></div> `);
    if (!values.online) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("address"))}>Address</label> <input${attr("id", id("address"))} type="text"${attr("value", values.address)}${attr("disabled", disabled, true)} class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none" placeholder="Street address"/></div> <div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("map-url"))}>Map URL</label> <input${attr("id", id("map-url"))} type="url"${attr("value", values.map_url)}${attr("disabled", disabled, true)} class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none" placeholder="https://..."/></div>`);
    } else {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> <div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("description"))}>Description</label> <span class="text-xs text-ash-500 mb-1 block">Supports <a href="https://www.markdownguide.org/basic-syntax/" target="_blank" rel="noopener noreferrer" class="underline text-ash-400 hover:text-ash-200">Markdown</a> formatting</span> <textarea${attr("id", id("description"))}${attr("disabled", disabled, true)} rows="3" class="w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200 focus:border-ash-500 focus:outline-none resize-none" placeholder="Optional description">`);
    const $$body = escape_html(values.description);
    if ($$body) {
      $$renderer2.push(`${$$body}`);
    }
    $$renderer2.push(`</textarea></div> <div class="grid grid-cols-1 sm:grid-cols-2 gap-4"><div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("standings"))}>Standings Visibility</label> `);
    $$renderer2.select(
      {
        id: id("standings"),
        value: values.standings_mode,
        disabled,
        onchange: (e) => handleInput("standings_mode", e.target.value),
        class: "w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
      },
      ($$renderer3) => {
        $$renderer3.option({ value: "Private" }, ($$renderer4) => {
          $$renderer4.push(`Private`);
        });
        $$renderer3.option({ value: "Cutoff" }, ($$renderer4) => {
          $$renderer4.push(`Cutoff (Top 5)`);
        });
        $$renderer3.option({ value: "Top 10" }, ($$renderer4) => {
          $$renderer4.push(`Top 10`);
        });
        $$renderer3.option({ value: "Public" }, ($$renderer4) => {
          $$renderer4.push(`Public`);
        });
      }
    );
    $$renderer2.push(`</div> <div><label class="block text-sm text-ash-400 mb-1"${attr("for", id("decklists"))}>Decklists Visibility</label> `);
    $$renderer2.select(
      {
        id: id("decklists"),
        value: values.decklists_mode,
        disabled,
        onchange: (e) => handleInput("decklists_mode", e.target.value),
        class: "w-full px-3 py-2 text-sm bg-dusk-950 border border-ash-700 rounded-lg text-ash-200"
      },
      ($$renderer3) => {
        $$renderer3.option({ value: "Winner" }, ($$renderer4) => {
          $$renderer4.push(`Winner Only`);
        });
        $$renderer3.option({ value: "Finalists" }, ($$renderer4) => {
          $$renderer4.push(`Finalists`);
        });
        $$renderer3.option({ value: "All" }, ($$renderer4) => {
          $$renderer4.push(`All`);
        });
      }
    );
    $$renderer2.push(`</div></div> <div class="space-y-3"><label class="flex items-center gap-3 cursor-pointer"><input type="checkbox"${attr("checked", values.proxies, true)}${attr("disabled", disabled, true)} class="w-5 h-5 rounded border-ash-700 bg-dusk-950 text-emerald-600 focus:ring-emerald-500"/> <span class="text-sm text-ash-200">Allow Proxies</span></label> <label class="flex items-center gap-3 cursor-pointer"><input type="checkbox"${attr("checked", values.multideck, true)}${attr("disabled", disabled, true)} class="w-5 h-5 rounded border-ash-700 bg-dusk-950 text-emerald-600 focus:ring-emerald-500"/> <span class="text-sm text-ash-200">Multideck</span></label> <label class="flex items-center gap-3 cursor-pointer"><input type="checkbox"${attr("checked", values.decklist_required, true)}${attr("disabled", disabled, true)} class="w-5 h-5 rounded border-ash-700 bg-dusk-950 text-emerald-600 focus:ring-emerald-500"/> <span class="text-sm text-ash-200">Decklist Required</span></label></div>`);
    bind_props($$props, { values });
  });
}
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    const canCreate = hasAnyRole("IC", "NC", "Prince");
    let values = {
      name: "",
      format: "Standard",
      rank: "",
      open_rounds: false,
      max_rounds: 0,
      online: false,
      country: "",
      venue: "",
      venue_url: "",
      address: "",
      map_url: "",
      start: "",
      finish: "",
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      description: "",
      standings_mode: "Private",
      decklists_mode: "Winner",
      proxies: false,
      multideck: false,
      decklist_required: false
    };
    let isSubmitting = false;
    let $$settled = true;
    let $$inner_renderer;
    function $$render_inner($$renderer3) {
      head("1sgxjv6", $$renderer3, ($$renderer4) => {
        $$renderer4.title(($$renderer5) => {
          $$renderer5.push(`<title>New Tournament - Archon</title>`);
        });
      });
      $$renderer3.push(`<div class="p-4 sm:p-8"><div class="max-w-2xl mx-auto"><div class="flex items-center gap-4 mb-6"><a href="/tournaments" class="text-ash-400 hover:text-ash-200">`);
      Icon($$renderer3, { icon: "lucide:arrow-left", class: "w-5 h-5" });
      $$renderer3.push(`<!----></a> <h1 class="text-3xl font-light text-crimson-500">New Tournament</h1></div> `);
      if (!canCreate) {
        $$renderer3.push("<!--[-->");
        $$renderer3.push(`<div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-4"><p class="text-crimson-300">Only IC, NC, or Prince can create tournaments.</p></div>`);
      } else {
        $$renderer3.push("<!--[!-->");
        $$renderer3.push(`<form class="space-y-6"><div class="bg-dusk-950 rounded-lg shadow p-6 border border-ash-800 space-y-4">`);
        {
          $$renderer3.push("<!--[!-->");
        }
        $$renderer3.push(`<!--]--> `);
        TournamentFields($$renderer3, {
          disabled: isSubmitting,
          get values() {
            return values;
          },
          set values($$value) {
            values = $$value;
            $$settled = false;
          }
        });
        $$renderer3.push(`<!----></div> <div class="flex gap-3 justify-end"><a href="/tournaments" class="px-4 py-2 text-sm font-medium text-ash-300 bg-ash-800 hover:bg-ash-700 rounded-lg transition-colors">Cancel</a> <button type="submit"${attr("disabled", !values.name.trim(), true)} class="px-4 py-2 text-sm font-medium text-bone-100 bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors shadow-md disabled:cursor-not-allowed">${escape_html("Create Tournament")}</button></div></form>`);
      }
      $$renderer3.push(`<!--]--></div></div>`);
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
