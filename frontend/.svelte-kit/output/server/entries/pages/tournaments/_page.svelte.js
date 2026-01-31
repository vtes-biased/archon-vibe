import { a3 as head, a1 as attr, Z as ensure_array_like, $ as stringify, _ as attr_class } from "../../../chunks/index2.js";
import "idb";
import { h as hasAnyRole } from "../../../chunks/auth.svelte.js";
import { a as getCountryFlag, g as getCountries } from "../../../chunks/geonames.js";
import { I as Icon } from "../../../chunks/Icon.js";
import { e as escape_html } from "../../../chunks/context.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let tournaments = [];
    let totalCount = 0;
    let searchQuery = "";
    let selectedState = "all";
    let selectedCountry = "all";
    let selectedFormat = "all";
    let sortBy = "date";
    let page = 0;
    const PAGE_SIZE = 50;
    const countries = getCountries();
    const states = ["Planned", "Registration", "Waiting", "Playing", "Finished"];
    const formats = ["Standard", "V5", "Limited"];
    const totalPages = Math.ceil(totalCount / PAGE_SIZE);
    const canCreate = hasAnyRole("IC", "NC", "Prince");
    function getStateBadgeClass(state) {
      switch (state) {
        case "Planned":
          return "bg-ash-800 text-ash-300";
        case "Registration":
          return "bg-emerald-900/60 text-emerald-300";
        case "Waiting":
          return "bg-amber-900/60 text-amber-300";
        case "Playing":
          return "bg-crimson-900/60 text-crimson-300";
        case "Finished":
          return "bg-ash-700 text-ash-400";
        default:
          return "bg-ash-800 text-ash-300";
      }
    }
    function formatDate(t) {
      if (!t.start) return "—";
      try {
        const tz = t.online ? void 0 : t.timezone || "UTC";
        const opts = {
          year: "numeric",
          month: "short",
          day: "numeric",
          ...tz ? { timeZone: tz } : {}
        };
        return new Date(t.start).toLocaleDateString(void 0, opts);
      } catch {
        return t.start;
      }
    }
    head("o4hasj", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>Tournaments - Archon</title>`);
      });
    });
    $$renderer2.push(`<div class="p-4 sm:p-8"><div class="max-w-6xl mx-auto"><div class="flex items-center justify-between mb-6"><h1 class="text-3xl font-light text-crimson-500">Tournaments</h1> `);
    if (canCreate) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<a href="/tournaments/new" class="px-4 py-2 text-sm font-medium text-bone-100 bg-emerald-700 hover:bg-emerald-600 rounded-lg transition-colors shadow-md">+ New Tournament</a>`);
    } else {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--></div> <div class="bg-dusk-950 rounded-lg shadow p-4 mb-6 border border-ash-800"><div class="flex flex-wrap gap-4"><div class="flex-1 min-w-[200px]"><label for="search" class="block text-sm font-medium text-ash-400 mb-1">Search</label> <input id="search" type="text"${attr("value", searchQuery)} placeholder="Search by name..." class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200 placeholder:text-ash-600"/></div> <div class="min-w-[150px]"><label for="state-filter" class="block text-sm font-medium text-ash-400 mb-1">State</label> `);
    $$renderer2.select(
      {
        id: "state-filter",
        value: selectedState,
        class: "w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200"
      },
      ($$renderer3) => {
        $$renderer3.option({ value: "all" }, ($$renderer4) => {
          $$renderer4.push(`All States`);
        });
        $$renderer3.push(`<!--[-->`);
        const each_array = ensure_array_like(states);
        for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
          let s = each_array[$$index];
          $$renderer3.option({ value: s }, ($$renderer4) => {
            $$renderer4.push(`${escape_html(s)}`);
          });
        }
        $$renderer3.push(`<!--]-->`);
      }
    );
    $$renderer2.push(`</div> <div class="min-w-[130px]"><label for="format-filter" class="block text-sm font-medium text-ash-400 mb-1">Format</label> `);
    $$renderer2.select(
      {
        id: "format-filter",
        value: selectedFormat,
        class: "w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200"
      },
      ($$renderer3) => {
        $$renderer3.option({ value: "all" }, ($$renderer4) => {
          $$renderer4.push(`All Formats`);
        });
        $$renderer3.push(`<!--[-->`);
        const each_array_1 = ensure_array_like(formats);
        for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
          let f = each_array_1[$$index_1];
          $$renderer3.option({ value: f }, ($$renderer4) => {
            $$renderer4.push(`${escape_html(f)}`);
          });
        }
        $$renderer3.push(`<!--]-->`);
      }
    );
    $$renderer2.push(`</div> <div class="min-w-[180px]"><label for="country-filter" class="block text-sm font-medium text-ash-400 mb-1">Country</label> `);
    $$renderer2.select(
      {
        id: "country-filter",
        value: selectedCountry,
        class: "w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200"
      },
      ($$renderer3) => {
        $$renderer3.option({ value: "all" }, ($$renderer4) => {
          $$renderer4.push(`All Countries`);
        });
        $$renderer3.push(`<!--[-->`);
        const each_array_2 = ensure_array_like(Object.entries(countries));
        for (let $$index_2 = 0, $$length = each_array_2.length; $$index_2 < $$length; $$index_2++) {
          let [code, country] = each_array_2[$$index_2];
          $$renderer3.option({ value: code }, ($$renderer4) => {
            $$renderer4.push(`${escape_html(country.name)} ${escape_html(getCountryFlag(code))}`);
          });
        }
        $$renderer3.push(`<!--]-->`);
      }
    );
    $$renderer2.push(`</div> <div class="min-w-[130px]"><label for="sort" class="block text-sm font-medium text-ash-400 mb-1">Sort by</label> `);
    $$renderer2.select(
      {
        id: "sort",
        value: sortBy,
        class: "w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200"
      },
      ($$renderer3) => {
        $$renderer3.option({ value: "date" }, ($$renderer4) => {
          $$renderer4.push(`Date`);
        });
        $$renderer3.option({ value: "name" }, ($$renderer4) => {
          $$renderer4.push(`Name`);
        });
        $$renderer3.option({ value: "state" }, ($$renderer4) => {
          $$renderer4.push(`State`);
        });
      }
    );
    $$renderer2.push(`</div></div></div> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (tournaments.length > 0) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div class="bg-dusk-950 rounded-lg shadow overflow-hidden border border-ash-800"><div class="hidden sm:grid sm:grid-cols-12 gap-4 px-6 py-3 bg-ash-900 text-sm font-medium text-ash-300 border-b border-ash-700"><div class="col-span-4">Name</div> <div class="col-span-2">Date</div> <div class="col-span-2">Country</div> <div class="col-span-2">Format</div> <div class="col-span-2">State</div></div> <div class="divide-y divide-ash-800"><!--[-->`);
      const each_array_3 = ensure_array_like(tournaments);
      for (let $$index_3 = 0, $$length = each_array_3.length; $$index_3 < $$length; $$index_3++) {
        let tournament = each_array_3[$$index_3];
        $$renderer2.push(`<a${attr("href", `/tournaments/${stringify(tournament.uid)}`)} class="block px-6 py-4 hover:bg-ash-900/50 transition-colors"><div class="sm:hidden space-y-2"><div class="flex items-start justify-between"><div><div class="font-semibold text-bone-100">${escape_html(tournament.name)}</div> <div class="text-sm text-ash-400 mt-1">${escape_html(formatDate(tournament))} `);
        if (tournament.country) {
          $$renderer2.push("<!--[-->");
          $$renderer2.push(`· ${escape_html(getCountryFlag(tournament.country))} ${escape_html(countries[tournament.country]?.name || tournament.country)}`);
        } else {
          $$renderer2.push("<!--[!-->");
        }
        $$renderer2.push(`<!--]--></div></div> <span${attr_class(`px-2 py-1 rounded text-xs font-medium ${stringify(getStateBadgeClass(tournament.state))}`)}>${escape_html(tournament.state)}</span></div> <div class="flex gap-2 text-xs text-ash-500"><span>${escape_html(tournament.format)}</span> `);
        if (tournament.rank) {
          $$renderer2.push("<!--[-->");
          $$renderer2.push(`<span>· ${escape_html(tournament.rank)}</span>`);
        } else {
          $$renderer2.push("<!--[!-->");
        }
        $$renderer2.push(`<!--]--> `);
        if (tournament.online) {
          $$renderer2.push("<!--[-->");
          $$renderer2.push(`<span>· Online</span>`);
        } else {
          $$renderer2.push("<!--[!-->");
        }
        $$renderer2.push(`<!--]--></div></div> <div class="hidden sm:grid sm:grid-cols-12 gap-4 items-center"><div class="col-span-4"><div class="font-semibold text-bone-100">${escape_html(tournament.name)}</div> `);
        if (tournament.rank) {
          $$renderer2.push("<!--[-->");
          $$renderer2.push(`<div class="text-xs text-ash-500">${escape_html(tournament.rank)}</div>`);
        } else {
          $$renderer2.push("<!--[!-->");
        }
        $$renderer2.push(`<!--]--></div> <div class="col-span-2 text-sm text-ash-400">${escape_html(formatDate(tournament))}</div> <div class="col-span-2 text-sm text-ash-400">`);
        if (tournament.country) {
          $$renderer2.push("<!--[-->");
          $$renderer2.push(`${escape_html(getCountryFlag(tournament.country))} ${escape_html(countries[tournament.country]?.name || tournament.country)}`);
        } else {
          $$renderer2.push("<!--[!-->");
          if (tournament.online) {
            $$renderer2.push("<!--[-->");
            $$renderer2.push(`Online`);
          } else {
            $$renderer2.push("<!--[!-->");
            $$renderer2.push(`—`);
          }
          $$renderer2.push(`<!--]-->`);
        }
        $$renderer2.push(`<!--]--></div> <div class="col-span-2 text-sm text-ash-400">${escape_html(tournament.format)}</div> <div class="col-span-2"><span${attr_class(`px-2 py-1 rounded text-xs font-medium ${stringify(getStateBadgeClass(tournament.state))}`)}>${escape_html(tournament.state)}</span></div></div></a>`);
      }
      $$renderer2.push(`<!--]--></div></div> <div class="mt-4 flex items-center justify-between text-sm text-ash-400"><span>${escape_html(totalCount)} tournament${escape_html("s")}</span> `);
      if (totalPages > 1) {
        $$renderer2.push("<!--[-->");
        $$renderer2.push(`<div class="flex items-center gap-2"><button${attr("disabled", page === 0, true)} class="px-3 py-1 rounded bg-ash-800 hover:bg-ash-700 disabled:opacity-40 disabled:cursor-not-allowed text-ash-200">Prev</button> <span>Page ${escape_html(page + 1)} of ${escape_html(totalPages)}</span> <button${attr("disabled", page >= totalPages - 1, true)} class="px-3 py-1 rounded bg-ash-800 hover:bg-ash-700 disabled:opacity-40 disabled:cursor-not-allowed text-ash-200">Next</button></div>`);
      } else {
        $$renderer2.push("<!--[!-->");
      }
      $$renderer2.push(`<!--]--></div>`);
    } else {
      $$renderer2.push("<!--[!-->");
      {
        $$renderer2.push("<!--[-->");
        $$renderer2.push(`<div class="text-center py-12"><div class="text-ash-500 mb-4">`);
        Icon($$renderer2, {
          icon: "lucide:loader-2",
          class: "mx-auto h-12 w-12 animate-spin"
        });
        $$renderer2.push(`<!----></div> <h3 class="text-lg font-medium text-bone-100 mb-2">Loading...</h3> <p class="text-ash-400">Loading tournaments from local storage.</p></div>`);
      }
      $$renderer2.push(`<!--]-->`);
    }
    $$renderer2.push(`<!--]--></div></div>`);
  });
}
export {
  _page as default
};
//# sourceMappingURL=_page.svelte.js.map
