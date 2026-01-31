import { a3 as head, Z as ensure_array_like, _ as attr_class, $ as stringify, a1 as attr } from "../../../chunks/index2.js";
import "idb";
import { g as getLastSyncTimestamp, d as deleteTournament, c as clearChangeForUid, s as setLastSyncTimestamp, a as saveUsersBatch, b as saveUser, e as deleteSanction, f as saveSanctionsBatch, h as saveSanction, i as saveTournamentsBatch, j as saveTournament, k as saveRatingsBatch, l as saveRating, m as clearAllUsers, n as clearAllSanctions, o as clearAllTournaments, p as clearAllRatings, q as clearChanges, r as clearLastSyncTimestamp } from "../../../chunks/db.js";
import { a as getAccessToken } from "../../../chunks/auth.svelte.js";
import { g as getCountries, a as getCountryFlag } from "../../../chunks/geonames.js";
import { I as Icon } from "../../../chunks/Icon.js";
import { e as escape_html } from "../../../chunks/context.js";
const API_URL = "http://localhost:8000";
const SPECS = [
  { batchType: "users", singleType: "user", save: saveUser, saveBatch: saveUsersBatch, del: async () => {
  } },
  { batchType: "sanctions", singleType: "sanction", save: saveSanction, saveBatch: saveSanctionsBatch, del: deleteSanction },
  { batchType: "tournaments", singleType: "tournament", save: saveTournament, saveBatch: saveTournamentsBatch, del: deleteTournament },
  { batchType: "ratings", singleType: "rating", save: saveRating, saveBatch: saveRatingsBatch, del: async () => {
  } }
];
class SyncManager {
  eventSource = null;
  listeners = [];
  reconnectAttempts = 0;
  maxReconnectAttempts = 5;
  reconnectDelay = 1e3;
  // Generic buffers keyed by batch type
  buffers = /* @__PURE__ */ new Map();
  isSynced = false;
  /**
   * Start syncing with the backend SSE stream.
   */
  async connect() {
    this.disconnect();
    this.isSynced = false;
    const lastSync = await getLastSyncTimestamp();
    const params = new URLSearchParams();
    if (lastSync) params.set("since", lastSync);
    const token = getAccessToken();
    if (token) params.set("token", token);
    const qs = params.toString();
    const url = qs ? `${API_URL}/stream?${qs}` : `${API_URL}/stream`;
    this.eventSource = new EventSource(url);
    this.eventSource.onopen = () => {
      this.reconnectAttempts = 0;
      this.reconnectDelay = 1e3;
      this.emit({ type: "connected" });
    };
    this.eventSource.onmessage = async (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "resync") {
          await this.clearAllStores();
          this.emit({ type: "resync" });
          return;
        }
        if (message.type === "tournament_delete") {
          const uid = message.data;
          await deleteTournament(uid);
          await clearChangeForUid(uid);
          this.emit({ type: "tournament" });
          return;
        }
        if (message.type === "sync_complete") {
          try {
            await this.flushAllBuffers();
          } catch (e) {
            console.error("Flush failed:", e);
          }
          try {
            if (message.timestamp) await setLastSyncTimestamp(message.timestamp);
          } catch (e) {
            console.error("Save timestamp failed:", e);
          }
          this.isSynced = true;
          this.emit({ type: "sync_complete", timestamp: message.timestamp });
          return;
        }
        for (const spec of SPECS) {
          if (message.type === spec.batchType) {
            const items = message.data;
            const buf = this.buffers.get(spec.batchType) || [];
            buf.push(...items);
            this.buffers.set(spec.batchType, buf);
            return;
          }
          if (message.type === spec.singleType) {
            const item = message.data;
            if (item.deleted_at) {
              await spec.del(item.uid);
            } else {
              await spec.save(item);
            }
            await clearChangeForUid(item.uid);
            this.emit({ type: spec.singleType, data: item });
            return;
          }
        }
      } catch (error) {
        console.error("Error processing SSE message:", error);
        this.emit({ type: "error", error: String(error) });
      }
    };
    this.eventSource.onerror = (error) => {
      console.error("SSE connection error:", error);
      this.disconnect();
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
        setTimeout(() => {
          this.connect();
        }, delay);
      } else {
        this.emit({ type: "error", error: "Failed to connect after multiple attempts" });
      }
    };
  }
  /**
   * Flush all buffered data to IndexedDB.
   */
  async flushAllBuffers() {
    for (const spec of SPECS) {
      const buf = this.buffers.get(spec.batchType);
      if (buf && buf.length > 0) {
        this.buffers.set(spec.batchType, []);
        try {
          const toSave = [];
          const toDelete = [];
          for (const item of buf) {
            if (item.deleted_at) {
              toDelete.push(item.uid);
            } else {
              toSave.push(item);
            }
          }
          if (toSave.length > 0) await spec.saveBatch(toSave);
          for (const uid of toDelete) await spec.del(uid);
        } catch (e) {
          console.error(`Flush ${spec.batchType} failed:`, e);
        }
      }
    }
  }
  /**
   * Clear all IndexedDB stores (used on resync and refresh).
   */
  async clearAllStores() {
    await clearAllUsers();
    await clearAllSanctions();
    await clearAllTournaments();
    await clearAllRatings();
    await clearChanges();
    await clearLastSyncTimestamp();
  }
  /**
   * Disconnect from SSE stream.
   */
  disconnect() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
      this.flushAllBuffers();
      this.emit({ type: "disconnected" });
    }
  }
  /**
   * Check if currently connected to SSE stream.
   */
  isConnected() {
    return this.eventSource !== null && this.eventSource.readyState === EventSource.OPEN;
  }
  /**
   * Perform a full refresh: clear local data and resync everything.
   */
  async refresh() {
    await this.clearAllStores();
    await this.connect();
  }
  addEventListener(callback) {
    this.listeners.push(callback);
  }
  removeEventListener(callback) {
    this.listeners = this.listeners.filter((cb) => cb !== callback);
  }
  emit(event) {
    this.listeners.forEach((callback) => callback(event));
  }
}
const syncManager = new SyncManager();
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let ratings = [];
    let userNames = /* @__PURE__ */ new Map();
    let isSyncing = !syncManager.isSynced;
    let selectedCategory = "constructed_offline";
    let selectedCountry = "all";
    let page = 0;
    const PAGE_SIZE = 50;
    const categories = [
      { value: "constructed_offline", label: "Constructed" },
      { value: "constructed_online", label: "Constructed Online" },
      { value: "limited_offline", label: "Limited" },
      { value: "limited_online", label: "Limited Online" }
    ];
    const countries = getCountries();
    const countryList = Object.entries(countries).map(([code, c]) => ({ code, name: c.name })).sort((a, b) => a.name.localeCompare(b.name));
    let filtered = () => {
      let result = ratings.filter((r) => {
        const cat = r[selectedCategory];
        return cat && cat.total > 0;
      });
      result.sort((a, b) => {
        const ta = a[selectedCategory]?.total ?? 0;
        const tb = b[selectedCategory]?.total ?? 0;
        return tb - ta;
      });
      return result;
    };
    let totalPages = Math.ceil(filtered().length / PAGE_SIZE);
    let paged = filtered().slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
    head("78bavc", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>Rankings - Archon</title>`);
      });
    });
    $$renderer2.push(`<div class="max-w-4xl mx-auto px-4 py-6"><h1 class="text-2xl font-bold text-ash-100 mb-4">Rankings</h1> <div class="flex gap-1 mb-4 overflow-x-auto"><!--[-->`);
    const each_array = ensure_array_like(categories);
    for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
      let cat = each_array[$$index];
      $$renderer2.push(`<button${attr_class(`px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${stringify(selectedCategory === cat.value ? "bg-crimson-900/60 text-crimson-300" : "bg-dusk-950 text-ash-400 hover:text-ash-200 hover:bg-ash-800/50")}`)}>${escape_html(cat.label)}</button>`);
    }
    $$renderer2.push(`<!--]--></div> <div class="mb-4">`);
    $$renderer2.select(
      {
        value: selectedCountry,
        class: "bg-dusk-950 border border-ash-800 rounded-lg px-3 py-2 text-sm text-ash-200 w-full sm:w-64"
      },
      ($$renderer3) => {
        $$renderer3.option({ value: "all" }, ($$renderer4) => {
          $$renderer4.push(`All countries`);
        });
        $$renderer3.push(`<!--[-->`);
        const each_array_1 = ensure_array_like(countryList);
        for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
          let c = each_array_1[$$index_1];
          $$renderer3.option({ value: c.code }, ($$renderer4) => {
            $$renderer4.push(`${escape_html(c.name)} ${escape_html(getCountryFlag(c.code))}`);
          });
        }
        $$renderer3.push(`<!--]-->`);
      }
    );
    $$renderer2.push(`</div> `);
    if (isSyncing && ratings.length === 0) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div class="text-center text-ash-400 py-8">`);
      Icon($$renderer2, {
        icon: "lucide:loader-2",
        class: "w-6 h-6 animate-spin inline-block"
      });
      $$renderer2.push(`<!----> <span class="ml-2">Loading rankings...</span></div>`);
    } else {
      $$renderer2.push("<!--[!-->");
      if (filtered().length === 0) {
        $$renderer2.push("<!--[-->");
        $$renderer2.push(`<div class="text-center text-ash-500 py-8">No rankings found</div>`);
      } else {
        $$renderer2.push("<!--[!-->");
        $$renderer2.push(`<div class="overflow-x-auto"><table class="w-full text-sm"><thead><tr class="border-b border-ash-800 text-ash-400"><th class="py-2 px-3 text-left w-12">#</th><th class="py-2 px-3 text-left">Player</th><th class="py-2 px-3 text-left">Country</th><th class="py-2 px-3 text-right">Points</th></tr></thead><tbody><!--[-->`);
        const each_array_2 = ensure_array_like(paged);
        for (let i = 0, $$length = each_array_2.length; i < $$length; i++) {
          let rating = each_array_2[i];
          const rank = page * PAGE_SIZE + i + 1;
          const total = rating[selectedCategory]?.total ?? 0;
          $$renderer2.push(`<tr class="border-b border-ash-800/50 hover:bg-ash-800/20"><td class="py-2 px-3 text-ash-400">${escape_html(rank)}</td><td class="py-2 px-3"><a${attr("href", `/users/${stringify(rating.user_uid)}`)} class="text-ash-100 hover:text-crimson-400">${escape_html(userNames.get(rating.user_uid) ?? "Unknown")}</a></td><td class="py-2 px-3 text-ash-300">`);
          if (rating.country) {
            $$renderer2.push("<!--[-->");
            $$renderer2.push(`${escape_html(getCountryFlag(rating.country))}
                  ${escape_html(countries[rating.country]?.name ?? rating.country)}`);
          } else {
            $$renderer2.push("<!--[!-->");
          }
          $$renderer2.push(`<!--]--></td><td class="py-2 px-3 text-right font-medium text-ash-100">${escape_html(total)}</td></tr>`);
        }
        $$renderer2.push(`<!--]--></tbody></table></div> `);
        if (totalPages > 1) {
          $$renderer2.push("<!--[-->");
          $$renderer2.push(`<div class="flex items-center justify-center gap-2 mt-4"><button${attr_class(`px-3 py-1 rounded text-sm ${stringify("text-ash-600 cursor-default")}`)}${attr("disabled", page === 0, true)}>`);
          Icon($$renderer2, { icon: "lucide:chevron-left", class: "w-4 h-4 inline" });
          $$renderer2.push(`<!----></button> <span class="text-sm text-ash-400">${escape_html(page + 1)} / ${escape_html(totalPages)}</span> <button${attr_class(`px-3 py-1 rounded text-sm ${stringify(page < totalPages - 1 ? "text-ash-200 hover:bg-ash-800/50" : "text-ash-600 cursor-default")}`)}${attr("disabled", page >= totalPages - 1, true)}>`);
          Icon($$renderer2, { icon: "lucide:chevron-right", class: "w-4 h-4 inline" });
          $$renderer2.push(`<!----></button></div>`);
        } else {
          $$renderer2.push("<!--[!-->");
        }
        $$renderer2.push(`<!--]-->`);
      }
      $$renderer2.push(`<!--]-->`);
    }
    $$renderer2.push(`<!--]--></div>`);
  });
}
export {
  _page as default
};
//# sourceMappingURL=_page.svelte.js.map
