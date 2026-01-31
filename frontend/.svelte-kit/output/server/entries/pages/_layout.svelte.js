import { Z as ensure_array_like, _ as attr_class, $ as stringify, a0 as store_get, a1 as attr, a2 as unsubscribe_stores } from "../../chunks/index2.js";
import { p as page } from "../../chunks/stores.js";
import "idb";
import { h as hasAnyRole } from "../../chunks/auth.svelte.js";
import { I as Icon } from "../../chunks/Icon.js";
import { g as getToasts } from "../../chunks/toast.svelte.js";
import { e as escape_html } from "../../chunks/context.js";
function Toast($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    const toasts = getToasts();
    function getIcon(type) {
      switch (type) {
        case "success":
          return "lucide:check-circle";
        case "error":
          return "lucide:x-circle";
        case "warning":
          return "lucide:alert-triangle";
        case "info":
          return "lucide:info";
      }
    }
    function getStyles(type) {
      switch (type) {
        case "success":
          return "bg-emerald-900/90 border-emerald-700 text-emerald-100";
        case "error":
          return "bg-crimson-900/90 border-crimson-700 text-crimson-100";
        case "warning":
          return "bg-amber-900/90 border-amber-700 text-amber-100";
        case "info":
          return "bg-dusk-900/90 border-ash-600 text-bone-100";
      }
    }
    function getIconColor(type) {
      switch (type) {
        case "success":
          return "text-emerald-400";
        case "error":
          return "text-crimson-400";
        case "warning":
          return "text-amber-400";
        case "info":
          return "text-ash-300";
      }
    }
    $$renderer2.push(`<div class="fixed top-4 right-4 z-[100] flex flex-col gap-2 max-w-sm w-full pointer-events-none"><!--[-->`);
    const each_array = ensure_array_like(toasts);
    for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
      let toast = each_array[$$index];
      $$renderer2.push(`<div${attr_class(`pointer-events-auto flex items-start gap-3 p-4 rounded-lg border shadow-lg backdrop-blur-sm animate-slide-in ${stringify(getStyles(toast.type))}`, "svelte-1cpok13")} role="alert">`);
      Icon($$renderer2, {
        icon: getIcon(toast.type),
        class: `w-5 h-5 flex-shrink-0 mt-0.5 ${stringify(getIconColor(toast.type))}`
      });
      $$renderer2.push(`<!----> <div class="flex-1 min-w-0"><p class="text-sm font-medium">${escape_html(toast.message)}</p> `);
      if (toast.action) {
        $$renderer2.push("<!--[-->");
        $$renderer2.push(`<button class="mt-2 text-sm font-medium underline hover:no-underline">${escape_html(toast.action.label)}</button>`);
      } else {
        $$renderer2.push("<!--[!-->");
      }
      $$renderer2.push(`<!--]--></div> <button class="flex-shrink-0 p-1 -m-1 rounded hover:bg-white/10 transition-colors" aria-label="Dismiss">`);
      Icon($$renderer2, { icon: "lucide:x", class: "w-4 h-4" });
      $$renderer2.push(`<!----></button></div>`);
    }
    $$renderer2.push(`<!--]--></div>`);
  });
}
function _layout($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    var $$store_subs;
    let { children } = $$props;
    let isOnline = navigator.onLine;
    let syncError = null;
    const baseNavItems = [
      { href: "/tournaments", label: "Tournaments", icon: "trophy" },
      { href: "/leagues", label: "Leagues", icon: "chart" },
      { href: "/rankings", label: "Rankings", icon: "ranking" },
      { href: "/users", label: "Users", icon: "users" },
      { href: "/profile", label: "Profile", icon: "user" }
    ];
    const navItems = hasAnyRole("DEV", "IC") ? [
      ...baseNavItems,
      { href: "/developer", label: "Developer", icon: "code" }
    ] : baseNavItems;
    function isActive(href, currentPath) {
      if (href === "/") return currentPath === "/";
      return currentPath.startsWith(href);
    }
    $$renderer2.push(`<div class="min-h-screen bg-bone-950 pb-16 sm:pb-0">`);
    if (!isOnline || syncError) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div${attr_class(`fixed top-0 left-0 right-0 z-50 px-4 py-2 text-center text-sm ${stringify(!isOnline ? "bg-amber-900/90 text-amber-100" : "bg-crimson-900/90 text-crimson-100")}`)}>`);
      if (!isOnline) {
        $$renderer2.push("<!--[-->");
        $$renderer2.push(`<span class="inline-flex items-center gap-2">`);
        Icon($$renderer2, { icon: "lucide:wifi-off", class: "w-4 h-4" });
        $$renderer2.push(`<!----> Offline - Changes will sync when reconnected</span>`);
      } else {
        $$renderer2.push("<!--[!-->");
        {
          $$renderer2.push("<!--[!-->");
        }
        $$renderer2.push(`<!--]-->`);
      }
      $$renderer2.push(`<!--]--></div>`);
    } else {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> <main class="sm:ml-20">`);
    children($$renderer2);
    $$renderer2.push(`<!----></main> <nav class="fixed bottom-0 left-0 right-0 z-40 bg-dusk-950 border-t border-ash-800 sm:hidden"><div class="flex justify-around"><!--[-->`);
    const each_array = ensure_array_like(navItems);
    for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
      let item = each_array[$$index];
      const active = isActive(item.href, store_get($$store_subs ??= {}, "$page", page).url.pathname);
      $$renderer2.push(`<a${attr("href", item.href)}${attr_class(`flex flex-col items-center py-2 px-3 min-w-[64px] ${stringify(active ? "text-crimson-500" : "text-ash-400 hover:text-ash-200")}`)}>`);
      if (item.icon === "trophy") {
        $$renderer2.push("<!--[-->");
        Icon($$renderer2, { icon: "lucide:trophy", class: "w-6 h-6" });
      } else {
        $$renderer2.push("<!--[!-->");
        if (item.icon === "chart") {
          $$renderer2.push("<!--[-->");
          Icon($$renderer2, { icon: "lucide:bar-chart-3", class: "w-6 h-6" });
        } else {
          $$renderer2.push("<!--[!-->");
          if (item.icon === "ranking") {
            $$renderer2.push("<!--[-->");
            Icon($$renderer2, { icon: "lucide:medal", class: "w-6 h-6" });
          } else {
            $$renderer2.push("<!--[!-->");
            if (item.icon === "users") {
              $$renderer2.push("<!--[-->");
              Icon($$renderer2, { icon: "lucide:users", class: "w-6 h-6" });
            } else {
              $$renderer2.push("<!--[!-->");
              if (item.icon === "user") {
                $$renderer2.push("<!--[-->");
                Icon($$renderer2, { icon: "lucide:user", class: "w-6 h-6" });
              } else {
                $$renderer2.push("<!--[!-->");
                if (item.icon === "code") {
                  $$renderer2.push("<!--[-->");
                  Icon($$renderer2, { icon: "lucide:code-2", class: "w-6 h-6" });
                } else {
                  $$renderer2.push("<!--[!-->");
                }
                $$renderer2.push(`<!--]-->`);
              }
              $$renderer2.push(`<!--]-->`);
            }
            $$renderer2.push(`<!--]-->`);
          }
          $$renderer2.push(`<!--]-->`);
        }
        $$renderer2.push(`<!--]-->`);
      }
      $$renderer2.push(`<!--]--> <span class="text-xs mt-1">${escape_html(item.label)}</span></a>`);
    }
    $$renderer2.push(`<!--]--></div></nav> <nav class="hidden sm:flex fixed left-0 top-0 bottom-0 w-20 bg-dusk-950 border-r border-ash-800 flex-col items-center py-4 z-40"><a href="/tournaments" class="mb-6 text-crimson-500 hover:text-crimson-400" title="Home"><img src="/favicon.svg" alt="Archon" class="w-16 h-16"/></a> <div class="flex-1 flex flex-col gap-2"><!--[-->`);
    const each_array_1 = ensure_array_like(navItems);
    for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
      let item = each_array_1[$$index_1];
      const active = isActive(item.href, store_get($$store_subs ??= {}, "$page", page).url.pathname);
      $$renderer2.push(`<a${attr("href", item.href)}${attr_class(`flex flex-col items-center py-3 px-2 rounded-lg transition-colors ${stringify(active ? "bg-crimson-900/50 text-crimson-400" : "text-ash-400 hover:text-ash-200 hover:bg-ash-800/50")}`)}${attr("title", item.label)}>`);
      if (item.icon === "trophy") {
        $$renderer2.push("<!--[-->");
        Icon($$renderer2, { icon: "lucide:trophy", class: "w-6 h-6" });
      } else {
        $$renderer2.push("<!--[!-->");
        if (item.icon === "chart") {
          $$renderer2.push("<!--[-->");
          Icon($$renderer2, { icon: "lucide:bar-chart-3", class: "w-6 h-6" });
        } else {
          $$renderer2.push("<!--[!-->");
          if (item.icon === "ranking") {
            $$renderer2.push("<!--[-->");
            Icon($$renderer2, { icon: "lucide:medal", class: "w-6 h-6" });
          } else {
            $$renderer2.push("<!--[!-->");
            if (item.icon === "users") {
              $$renderer2.push("<!--[-->");
              Icon($$renderer2, { icon: "lucide:users", class: "w-6 h-6" });
            } else {
              $$renderer2.push("<!--[!-->");
              if (item.icon === "user") {
                $$renderer2.push("<!--[-->");
                Icon($$renderer2, { icon: "lucide:user", class: "w-6 h-6" });
              } else {
                $$renderer2.push("<!--[!-->");
                if (item.icon === "code") {
                  $$renderer2.push("<!--[-->");
                  Icon($$renderer2, { icon: "lucide:code-2", class: "w-6 h-6" });
                } else {
                  $$renderer2.push("<!--[!-->");
                }
                $$renderer2.push(`<!--]-->`);
              }
              $$renderer2.push(`<!--]-->`);
            }
            $$renderer2.push(`<!--]-->`);
          }
          $$renderer2.push(`<!--]-->`);
        }
        $$renderer2.push(`<!--]-->`);
      }
      $$renderer2.push(`<!--]--> <span class="text-xs mt-1">${escape_html(item.label)}</span></a>`);
    }
    $$renderer2.push(`<!--]--></div> <div class="mt-auto pt-4"><div${attr_class(`w-3 h-3 rounded-full ${stringify(isOnline ? "bg-amber-500 animate-pulse" : "bg-crimson-500")}`)}${attr("title", isOnline ? "Syncing..." : "Offline")}></div></div></nav> `);
    Toast($$renderer2);
    $$renderer2.push(`<!----></div>`);
    if ($$store_subs) unsubscribe_stores($$store_subs);
  });
}
export {
  _layout as default
};
//# sourceMappingURL=_layout.svelte.js.map
