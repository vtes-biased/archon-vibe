import { _ as attr_class, a1 as attr, a4 as bind_props, $ as stringify, Z as ensure_array_like, a5 as clsx, a3 as head } from "../../../chunks/index2.js";
import "idb";
import { s as showToast } from "../../../chunks/toast.svelte.js";
import { a as getAccessToken } from "../../../chunks/auth.svelte.js";
import { g as getCountries, a as getCountryFlag } from "../../../chunks/geonames.js";
import { t as getRoleClasses, u as expandRolesForFilter, v as getFilteredUsers, w as userHasPastSanctions, x as isUserCurrentlySanctioned, y as hasAnyUsers } from "../../../chunks/db.js";
import "../../../chunks/functions.js";
import { I as Icon } from "../../../chunks/Icon.js";
import { e as escape_html } from "../../../chunks/context.js";
import "clsx";
const API_URL = "http://localhost:8000";
class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
    this.name = "ApiError";
  }
}
async function apiRequest(path, options = {}) {
  const token = getAccessToken();
  const headers = {
    ...options.headers || {}
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (options.body && typeof options.body === "string") {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers
  });
  if (!response.ok) {
    let detail;
    try {
      const data = await response.json();
      detail = data.detail || data.message;
    } catch {
    }
    const message = detail || `Request failed: ${response.statusText}`;
    showToast({ type: "error", message });
    throw new ApiError(message, response.status, detail);
  }
  return response.json();
}
function isOnline() {
  return navigator.onLine;
}
async function updateUser(uid, name, country, vekn_id, city, nickname, roles) {
  if (!isOnline()) {
    throw new Error("Cannot update users while offline. Please connect to the internet.");
  }
  const params = new URLSearchParams();
  if (name) params.append("name", name);
  if (country) params.append("country", country);
  if (city !== void 0) params.append("city", city || "");
  if (nickname !== void 0) params.append("nickname", nickname || "");
  if (roles !== void 0) {
    if (roles.length === 0) {
      params.append("roles", "");
    } else {
      roles.forEach((role) => params.append("roles", role));
    }
  }
  return apiRequest(`/api/users/${uid}?${params}`, { method: "PUT" });
}
function CityAutocomplete($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let {
      value = "",
      countryCode,
      disabled = false,
      required = false,
      class: className = "",
      onselect
    } = $$props;
    let inputValue = value;
    $$renderer2.push(`<div${attr_class(`relative ${stringify(className)}`)}><input type="text"${attr("value", inputValue)}${attr("disabled", disabled, true)}${attr("required", required, true)}${attr("placeholder", disabled ? "Select a country first" : "Start typing city name...")} class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 placeholder:text-mist-dark focus:ring-2 focus:ring-crimson-500 focus:border-transparent disabled:bg-ash-900 disabled:text-mist-dark disabled:cursor-not-allowed"/> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--></div>`);
    bind_props($$props, { value });
  });
}
function VeknManagement($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { user } = $$props;
    $$renderer2.push(`<fieldset class="border border-ash-700 rounded p-4"><legend class="text-sm font-medium text-ash-400 px-2">VEKN</legend> <p class="text-sm text-ash-300 mb-2">`);
    if (user.vekn_id) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`ID: ${escape_html(user.vekn_id)}`);
    } else {
      $$renderer2.push("<!--[!-->");
      $$renderer2.push(`No VEKN ID`);
    }
    $$renderer2.push(`<!--]--></p> <div class="flex flex-wrap gap-2">`);
    if (!user.vekn_id) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<button type="button" class="px-3 py-1 text-xs bg-emerald-800 hover:bg-emerald-700 text-bone-100 rounded transition-colors" title="Allocate new VEKN ID">`);
      Icon($$renderer2, { icon: "lucide:user-plus", class: "inline w-3 h-3 mr-1" });
      $$renderer2.push(`<!----> Sponsor</button> <button type="button" class="px-3 py-1 text-xs bg-ash-700 hover:bg-ash-600 text-bone-100 rounded transition-colors" title="Link existing VEKN ID">`);
      Icon($$renderer2, { icon: "lucide:link", class: "inline w-3 h-3 mr-1" });
      $$renderer2.push(`<!----> Link VEKN</button>`);
    } else {
      $$renderer2.push("<!--[!-->");
      $$renderer2.push(`<button type="button" class="px-3 py-1 text-xs bg-crimson-800 hover:bg-crimson-700 text-bone-100 rounded transition-colors" title="Remove VEKN ID from user">`);
      Icon($$renderer2, { icon: "lucide:unlink", class: "inline w-3 h-3 mr-1" });
      $$renderer2.push(`<!----> Force Abandon</button>`);
    }
    $$renderer2.push(`<!--]--> <button type="button" class="px-3 py-1 text-xs bg-ash-700 hover:bg-ash-600 text-bone-100 rounded transition-colors" title="Merge with another user">`);
    Icon($$renderer2, { icon: "lucide:git-merge", class: "inline w-3 h-3 mr-1" });
    $$renderer2.push(`<!----> Merge</button></div></fieldset> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]-->`);
  });
}
function SanctionBadge($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { sanction } = $$props;
    const isLifted = sanction.lifted_at !== null;
    const isExpired = () => {
      if (!sanction.expires_at) return false;
      return new Date(sanction.expires_at) < /* @__PURE__ */ new Date();
    };
    const isPermanent = sanction.level === "suspension" && !sanction.expires_at;
    const isInactive = isLifted || isExpired();
    const SANCTION_COLORS = {
      caution: { bg: "bg-yellow-900/60", text: "text-yellow-200" },
      warning: { bg: "bg-orange-900/60", text: "text-orange-200" },
      disqualification: { bg: "bg-red-900/60", text: "text-red-200" },
      suspension: { bg: "bg-crimson-900/80", text: "text-crimson-200" },
      probation: { bg: "bg-rose-900/60", text: "text-rose-200" },
      score_adjustment: { bg: "bg-gray-800/60", text: "text-gray-200" }
    };
    const levelLabels = {
      caution: "Caution",
      warning: "Warning",
      disqualification: "DQ",
      suspension: "Suspension",
      probation: "Probation",
      score_adjustment: "Score Adj"
    };
    const colors = SANCTION_COLORS[sanction.level];
    const label = levelLabels[sanction.level];
    const formatDate = (dateStr) => {
      return new Date(dateStr).toLocaleDateString();
    };
    const tooltipText = () => {
      let text = `${label}: ${sanction.description}
Issued: ${formatDate(sanction.issued_at)}`;
      if (sanction.expires_at) {
        text += `
Expires: ${formatDate(sanction.expires_at)}`;
      }
      if (isLifted && sanction.lifted_at) {
        text += `
Lifted: ${formatDate(sanction.lifted_at)}`;
      }
      if (isPermanent) {
        text += "\nPermanent ban";
      }
      return text;
    };
    $$renderer2.push(`<span${attr_class(`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${stringify(colors.bg)} ${stringify(colors.text)} ${stringify(isInactive ? "line-through opacity-60" : "")}`)}${attr("title", tooltipText())}>`);
    if (isPermanent) {
      $$renderer2.push("<!--[-->");
      Icon($$renderer2, { icon: "lucide:ban", class: "w-3 h-3" });
    } else {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> ${escape_html(label)} `);
    if (isLifted) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<span title="Lifted">`);
      Icon($$renderer2, { icon: "lucide:check", class: "w-3 h-3" });
      $$renderer2.push(`<!----></span>`);
    } else {
      $$renderer2.push("<!--[!-->");
      if (isExpired()) {
        $$renderer2.push("<!--[-->");
        $$renderer2.push(`<span title="Expired">`);
        Icon($$renderer2, { icon: "lucide:clock", class: "w-3 h-3" });
        $$renderer2.push(`<!----></span>`);
      } else {
        $$renderer2.push("<!--[!-->");
      }
      $$renderer2.push(`<!--]-->`);
    }
    $$renderer2.push(`<!--]--></span>`);
  });
}
function SanctionsManager($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let { user, canIssueSanctions } = $$props;
    let userSanctions = [];
    if (canIssueSanctions) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<fieldset class="border border-crimson-800/50 rounded p-4"><legend class="text-sm font-medium text-crimson-400 px-2">Sanctions</legend> `);
      if (userSanctions.length > 0) {
        $$renderer2.push("<!--[-->");
        $$renderer2.push(`<div class="mb-4 space-y-2"><!--[-->`);
        const each_array = ensure_array_like(userSanctions);
        for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
          let sanction = each_array[$$index];
          $$renderer2.push(`<button type="button" class="w-full flex items-center justify-between gap-2 p-2 bg-dusk-900 rounded border border-ash-700 hover:border-ash-600 transition-colors text-left"><div class="flex-1 min-w-0"><div class="flex items-center gap-2">`);
          SanctionBadge($$renderer2, { sanction });
          $$renderer2.push(`<!----> <span class="text-xs text-ash-400 truncate">${escape_html(sanction.description)}</span></div> <div class="text-xs text-ash-500 mt-1">${escape_html(new Date(sanction.issued_at).toLocaleDateString())} `);
          if (sanction.expires_at) {
            $$renderer2.push("<!--[-->");
            $$renderer2.push(`→ ${escape_html(new Date(sanction.expires_at).toLocaleDateString())}`);
          } else {
            $$renderer2.push("<!--[!-->");
          }
          $$renderer2.push(`<!--]--></div></div> `);
          Icon($$renderer2, { icon: "lucide:pencil", class: "w-4 h-4 text-ash-500" });
          $$renderer2.push(`<!----></button>`);
        }
        $$renderer2.push(`<!--]--></div>`);
      } else {
        $$renderer2.push("<!--[!-->");
      }
      $$renderer2.push(`<!--]--> <div class="flex flex-wrap gap-2"><button type="button" class="px-3 py-1 text-xs bg-crimson-800 hover:bg-crimson-700 text-bone-100 rounded transition-colors" title="Issue a sanction">`);
      Icon($$renderer2, { icon: "lucide:alert-triangle", class: "inline w-3 h-3 mr-1" });
      $$renderer2.push(`<!----> Issue Sanction</button></div></fieldset>`);
    } else {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (!canIssueSanctions && userSanctions.length > 0) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div class="flex items-start gap-2"><span class="font-medium">Sanctions:</span> <div class="flex flex-wrap gap-1"><!--[-->`);
      const each_array_1 = ensure_array_like(userSanctions);
      for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
        let sanction = each_array_1[$$index_1];
        SanctionBadge($$renderer2, { sanction });
      }
      $$renderer2.push(`<!--]--></div></div>`);
    } else {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]-->`);
  });
}
function User($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let {
      user,
      mode = "view",
      editable = true,
      inline = false,
      showManagement = false,
      onupdated,
      oncreated,
      oncancel,
      oneditingchange
    } = $$props;
    const canManage = () => {
      return false;
    };
    const canIssueSanctions = () => {
      return false;
    };
    function canChangeRole(role) {
      return false;
    }
    const canEditAvatar = () => {
      return false;
    };
    const isEditing = mode === "edit" || mode === "create";
    let editName = "";
    let editCountry = "";
    let editCity = "";
    let editNickname = "";
    let editEmail = "";
    let editRoles = [];
    let saving = false;
    let error = "";
    async function autoSave() {
      if (mode === "create" || !user) return;
      if (!editName.trim() || !editCountry.trim()) {
        error = "Name and country are required";
        return;
      }
      try {
        saving = true;
        error = "";
        const updated = await updateUser(
          user.uid,
          editName.trim(),
          editCountry.trim().toUpperCase(),
          void 0,
          // VEKN ID managed via Sponsor/Link/Abandon only
          editCity.trim() || null,
          editNickname.trim() || null,
          editRoles
        );
        onupdated?.(updated);
      } catch (e) {
        error = e instanceof Error ? e.message : "Failed to save";
      } finally {
        saving = false;
      }
    }
    function immediateAutoSave() {
      autoSave();
    }
    const countries = getCountries();
    const sortedCountries = Object.values(countries).sort((a, b) => a.name.localeCompare(b.name));
    const availableRoles = [
      "IC",
      "NC",
      "Prince",
      "Ethics",
      "PTC",
      "PT",
      "Rulemonger",
      "Judge",
      "Judgekin",
      "DEV"
    ];
    let $$settled = true;
    let $$inner_renderer;
    function $$render_inner($$renderer3) {
      $$renderer3.push(`<div${attr_class(clsx(inline ? "p-4" : "bg-dusk-950 rounded-lg shadow p-4 hover:shadow-md transition-shadow border border-ash-800"))}>`);
      if (isEditing) {
        $$renderer3.push("<!--[-->");
        $$renderer3.push(`<div role="presentation"><form class="space-y-4">`);
        if (mode !== "create") {
          $$renderer3.push("<!--[-->");
          $$renderer3.push(`<div class="flex justify-end -mt-1 -mr-1"><button type="button" class="p-2 text-ash-500 hover:text-crimson-400 transition-colors" title="Close">`);
          Icon($$renderer3, { icon: "lucide:x", class: "w-5 h-5" });
          $$renderer3.push(`<!----></button></div>`);
        } else {
          $$renderer3.push("<!--[!-->");
        }
        $$renderer3.push(`<!--]--> <div><label for="edit-name" class="block text-sm font-medium text-ash-400 mb-1">Name *</label> <input id="edit-name" type="text"${attr("value", editName)} required class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"/></div> `);
        if (mode === "create") {
          $$renderer3.push("<!--[-->");
          $$renderer3.push(`<div><label for="edit-email" class="block text-sm font-medium text-ash-400 mb-1">Email (optional)</label> <input id="edit-email" type="email"${attr("value", editEmail)} placeholder="user@example.com" class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"/> <p class="mt-1 text-xs text-ash-500">If provided, an invite email will be sent so they can log in.</p></div>`);
        } else {
          $$renderer3.push("<!--[!-->");
          if (!canManage()) {
            $$renderer3.push("<!--[-->");
            $$renderer3.push(`<div><span class="block text-sm font-medium text-ash-400 mb-1">VEKN ID</span> <span class="block px-3 py-2 text-ash-300">${escape_html(user?.vekn_id || "—")}</span></div>`);
          } else {
            $$renderer3.push("<!--[!-->");
          }
          $$renderer3.push(`<!--]-->`);
        }
        $$renderer3.push(`<!--]--> <div><label for="edit-country" class="block text-sm font-medium text-ash-400 mb-1">Country *</label> `);
        $$renderer3.select(
          {
            id: "edit-country",
            value: editCountry,
            required: true,
            onchange: () => {
              if (editCity) {
                editCity = "";
              }
              if (mode !== "create") immediateAutoSave();
            },
            class: "w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"
          },
          ($$renderer4) => {
            $$renderer4.option({ value: "" }, ($$renderer5) => {
              $$renderer5.push(`Select a country...`);
            });
            $$renderer4.push(`<!--[-->`);
            const each_array = ensure_array_like(sortedCountries);
            for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
              let country = each_array[$$index];
              $$renderer4.option({ value: country.iso_code }, ($$renderer5) => {
                $$renderer5.push(`${escape_html(country.name)} ${escape_html(getCountryFlag(country.iso_code))}`);
              });
            }
            $$renderer4.push(`<!--]-->`);
          }
        );
        $$renderer3.push(`</div> <div><label for="edit-city" class="block text-sm font-medium text-ash-400 mb-1">City</label> `);
        CityAutocomplete($$renderer3, {
          countryCode: editCountry,
          disabled: !editCountry,
          onselect: () => mode !== "create" && immediateAutoSave(),
          get value() {
            return editCity;
          },
          set value($$value) {
            editCity = $$value;
            $$settled = false;
          }
        });
        $$renderer3.push(`<!----> `);
        {
          $$renderer3.push("<!--[-->");
          $$renderer3.push(`<p class="mt-1 text-xs text-mist-dark">Select a country first to search for cities</p>`);
        }
        $$renderer3.push(`<!--]--></div> <div><label for="edit-nickname" class="block text-sm font-medium text-ash-400 mb-1">Nickname</label> <input id="edit-nickname" type="text"${attr("value", editNickname)} class="w-full px-3 py-2 border border-ash-600 rounded bg-dusk-950 text-ash-200 focus:ring-2 focus:ring-crimson-500 focus:border-transparent"/></div> <fieldset><legend class="block text-sm font-medium text-ash-400 mb-2">Roles</legend> <div class="flex flex-wrap gap-2"><!--[-->`);
        const each_array_1 = ensure_array_like(availableRoles);
        for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
          let role = each_array_1[$$index_1];
          const allowed = canChangeRole();
          $$renderer3.push(`<button type="button"${attr("disabled", !allowed, true)}${attr("title", allowed ? `Toggle ${role}` : `You cannot change ${role}`)}${attr_class(`px-3 py-1 rounded text-sm font-medium transition-colors ${stringify(editRoles.includes(role) ? getRoleClasses(role) : "bg-ash-800 text-ash-400")} ${stringify(allowed ? "hover:opacity-80 cursor-pointer" : "opacity-50 cursor-not-allowed")}`)}>${escape_html(role)}</button>`);
        }
        $$renderer3.push(`<!--]--></div> `);
        if (mode !== "create" && user && !user.vekn_id) {
          $$renderer3.push("<!--[-->");
          $$renderer3.push(`<p class="mt-2 text-xs text-crimson-400">User must have a VEKN ID to be assigned roles</p>`);
        } else {
          $$renderer3.push("<!--[!-->");
        }
        $$renderer3.push(`<!--]--></fieldset> `);
        if (mode !== "create" && canManage() && user) {
          $$renderer3.push("<!--[-->");
          VeknManagement($$renderer3, { user });
        } else {
          $$renderer3.push("<!--[!-->");
        }
        $$renderer3.push(`<!--]--> `);
        if (mode !== "create" && user) {
          $$renderer3.push("<!--[-->");
          SanctionsManager($$renderer3, { user, canIssueSanctions: canIssueSanctions() });
        } else {
          $$renderer3.push("<!--[!-->");
        }
        $$renderer3.push(`<!--]--> `);
        if (error) {
          $$renderer3.push("<!--[-->");
          $$renderer3.push(`<div class="text-sm text-crimson-400">${escape_html(error)}</div>`);
        } else {
          $$renderer3.push("<!--[!-->");
        }
        $$renderer3.push(`<!--]--> `);
        if (mode === "create") {
          $$renderer3.push("<!--[-->");
          $$renderer3.push(`<div class="flex gap-2 pt-2"><button type="submit"${attr("disabled", saving, true)} class="flex-1 px-4 py-2 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 text-bone-100 rounded font-medium transition-colors disabled:cursor-not-allowed">${escape_html(saving ? "Creating..." : "Create User")}</button> <button type="button"${attr("disabled", saving, true)} class="px-4 py-2 bg-ash-700 hover:bg-ash-600 text-ash-200 rounded font-medium transition-colors disabled:cursor-not-allowed">Cancel</button></div>`);
        } else {
          $$renderer3.push("<!--[!-->");
        }
        $$renderer3.push(`<!--]--></form></div>`);
      } else {
        $$renderer3.push("<!--[!-->");
        if (user) {
          $$renderer3.push("<!--[-->");
          $$renderer3.push(`<div class="flex items-start justify-between"><div class="mr-4 flex-shrink-0">`);
          if (canEditAvatar()) {
            $$renderer3.push("<!--[-->");
            $$renderer3.push(`<button class="relative group" title="Change avatar">`);
            if (user.avatar_path) {
              $$renderer3.push("<!--[-->");
              $$renderer3.push(`<img${attr("src", user.avatar_path)}${attr("alt", `${stringify(user.name)}'s avatar`)} class="w-16 h-16 rounded-full object-cover ring-2 ring-ash-700 group-hover:ring-crimson-500 transition-all"/>`);
            } else {
              $$renderer3.push("<!--[!-->");
              $$renderer3.push(`<div class="w-16 h-16 rounded-full bg-ash-800 flex items-center justify-center ring-2 ring-ash-700 group-hover:ring-crimson-500 transition-all">`);
              Icon($$renderer3, { icon: "lucide:user", class: "w-8 h-8 text-ash-500" });
              $$renderer3.push(`<!----></div>`);
            }
            $$renderer3.push(`<!--]--> <div class="absolute inset-0 rounded-full bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">`);
            Icon($$renderer3, { icon: "lucide:camera", class: "w-5 h-5 text-white" });
            $$renderer3.push(`<!----></div></button>`);
          } else {
            $$renderer3.push("<!--[!-->");
            if (user.avatar_path) {
              $$renderer3.push("<!--[-->");
              $$renderer3.push(`<img${attr("src", user.avatar_path)}${attr("alt", `${stringify(user.name)}'s avatar`)} class="w-16 h-16 rounded-full object-cover ring-2 ring-ash-700"/>`);
            } else {
              $$renderer3.push("<!--[!-->");
              $$renderer3.push(`<div class="w-16 h-16 rounded-full bg-ash-800 flex items-center justify-center ring-2 ring-ash-700">`);
              Icon($$renderer3, { icon: "lucide:user", class: "w-8 h-8 text-ash-500" });
              $$renderer3.push(`<!----></div>`);
            }
            $$renderer3.push(`<!--]-->`);
          }
          $$renderer3.push(`<!--]--></div> <div class="flex-1"><h3 class="text-lg font-semibold text-bone-100">${escape_html(user.name)}</h3> <div class="mt-2 space-y-1 text-sm text-ash-400">`);
          if (user.vekn_id) {
            $$renderer3.push("<!--[-->");
            $$renderer3.push(`<div class="flex items-center gap-2"><span class="font-medium">VEKN ID:</span> <span>${escape_html(user.vekn_id)}</span></div>`);
          } else {
            $$renderer3.push("<!--[!-->");
          }
          $$renderer3.push(`<!--]--> `);
          if (user.nickname) {
            $$renderer3.push("<!--[-->");
            $$renderer3.push(`<div class="flex items-center gap-2"><span class="font-medium">Nickname:</span> <span>${escape_html(user.nickname)}</span></div>`);
          } else {
            $$renderer3.push("<!--[!-->");
          }
          $$renderer3.push(`<!--]--> <div class="flex items-center gap-2"><span class="font-medium">Country:</span> <span>${escape_html(user.country ? `${getCountryFlag(user.country)} ${countries[user.country]?.name || user.country}` : "N/A")}</span></div> `);
          if (user.city) {
            $$renderer3.push("<!--[-->");
            $$renderer3.push(`<div class="flex items-center gap-2"><span class="font-medium">City:</span> <span>${escape_html(user.city)}</span></div>`);
          } else {
            $$renderer3.push("<!--[!-->");
          }
          $$renderer3.push(`<!--]--> `);
          if (user.roles.length > 0) {
            $$renderer3.push("<!--[-->");
            $$renderer3.push(`<div class="flex items-start gap-2"><span class="font-medium">Roles:</span> <div class="flex flex-wrap gap-1"><!--[-->`);
            const each_array_2 = ensure_array_like(user.roles);
            for (let $$index_2 = 0, $$length = each_array_2.length; $$index_2 < $$length; $$index_2++) {
              let role = each_array_2[$$index_2];
              $$renderer3.push(`<span${attr_class(`px-2 py-0.5 rounded text-xs font-medium ${stringify(getRoleClasses(role))}`)}>${escape_html(role)}</span>`);
            }
            $$renderer3.push(`<!--]--></div></div>`);
          } else {
            $$renderer3.push("<!--[!-->");
          }
          $$renderer3.push(`<!--]--> `);
          SanctionsManager($$renderer3, { user, canIssueSanctions: false });
          $$renderer3.push(`<!----></div></div> `);
          if (editable) {
            $$renderer3.push("<!--[-->");
            $$renderer3.push(`<button class="ml-2 p-2 text-ash-500 hover:text-crimson-400 transition-colors" title="Edit user">`);
            Icon($$renderer3, { icon: "lucide:square-pen", class: "w-5 h-5" });
            $$renderer3.push(`<!----></button>`);
          } else {
            $$renderer3.push("<!--[!-->");
          }
          $$renderer3.push(`<!--]--></div> <div class="mt-3 pt-3 border-t border-ash-700"><p class="text-xs text-mist-dark">Last modified: ${escape_html(new Date(user.modified).toLocaleString())}</p></div>`);
        } else {
          $$renderer3.push("<!--[!-->");
          $$renderer3.push(`<div class="text-crimson-400">Invalid user component state</div>`);
        }
        $$renderer3.push(`<!--]-->`);
      }
      $$renderer3.push(`<!--]--></div> `);
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
class DisplayContext {
  filters = {};
  pagination = {
    currentPage: 1,
    pageSize: 250
  };
  /**
   * Update the current display filters.
   */
  setFilters(country, roles, nameSearch, hasPastSanctions, currentlySanctioned) {
    this.filters = {
      country: country && country !== "all" ? country : void 0,
      roles: roles && roles.length > 0 ? [...roles] : void 0,
      // Convert Svelte proxy
      nameSearch: nameSearch && nameSearch.trim() ? nameSearch.trim().toLowerCase() : void 0,
      hasPastSanctions: hasPastSanctions || void 0,
      currentlySanctioned: currentlySanctioned || void 0
    };
    this.pagination.currentPage = 1;
  }
  /**
   * Update pagination context with currently visible users.
   */
  setPagination(currentPage, pageSize, visibleUsers) {
    this.pagination = {
      currentPage,
      pageSize,
      firstVisibleName: visibleUsers[0]?.name,
      lastVisibleName: visibleUsers[visibleUsers.length - 1]?.name
    };
  }
  /**
   * Get the current display filters.
   */
  getFilters() {
    return { ...this.filters };
  }
  /**
   * Check if a user matches the current display context (filters + pagination).
   *
   * Returns true if the user update should trigger a display refresh.
   * Takes into account both filter criteria and pagination/ordering.
   */
  matchesCurrentFilters(user) {
    const { country, roles, nameSearch } = this.filters;
    if (country && user.country !== country) {
      return false;
    }
    if (roles && roles.length > 0) {
      const plainRoles = [...roles];
      const expandedRoles = expandRolesForFilter(plainRoles);
      const hasMatchingRole = expandedRoles.some((role) => user.roles.includes(role));
      if (!hasMatchingRole) {
        return false;
      }
    }
    if (nameSearch) {
      const nameLower = user.name.toLowerCase();
      const words = nameLower.split(/\s+/);
      const matchesName = words.some((word) => word.startsWith(nameSearch));
      if (!matchesName) {
        return false;
      }
    }
    if (this.pagination.currentPage === 1) {
      return true;
    }
    if (!this.pagination.firstVisibleName || !this.pagination.lastVisibleName) {
      return true;
    }
    const userName = user.name;
    const { firstVisibleName, lastVisibleName } = this.pagination;
    return userName.localeCompare(firstVisibleName) >= 0 && userName.localeCompare(lastVisibleName) <= 0;
  }
  /**
   * Check if any filters are currently active.
   */
  hasActiveFilters() {
    return !!(this.filters.country || this.filters.roles && this.filters.roles.length > 0 || this.filters.nameSearch || this.filters.hasPastSanctions || this.filters.currentlySanctioned);
  }
}
const displayContext = new DisplayContext();
function UserList($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    let filteredUsers = [];
    let error = null;
    let isOnline2 = navigator.onLine;
    let hasLoadedOnce = false;
    let editingUserId = null;
    let expandedUserId = null;
    let isUserEditing = false;
    let currentPage = 1;
    let pageSize = 250;
    let selectedCountry = "all";
    let selectedRoles = [];
    let searchQuery = "";
    let filterHasPastSanctions = false;
    let filterCurrentlySanctioned = false;
    let displayRefreshTimer;
    let isLoadingUsers = false;
    const countries = getCountries();
    const availableRoles = ["IC", "NC", "Prince", "Ethics", "PTC", "PT", "Judge", "DEV"];
    let paginatedUsers = () => {
      const start = (currentPage - 1) * pageSize;
      const end = start + pageSize;
      return filteredUsers.slice(start, end);
    };
    let totalPages = Math.ceil(filteredUsers.length / pageSize);
    async function loadUsers() {
      if (isLoadingUsers) {
        scheduleDisplayRefresh();
        return;
      }
      isLoadingUsers = true;
      try {
        error = null;
        const {
          country,
          roles,
          nameSearch,
          hasPastSanctions,
          currentlySanctioned
        } = displayContext.getFilters();
        let users = await getFilteredUsers(country, roles, nameSearch);
        if (hasPastSanctions || currentlySanctioned) {
          const sanctionChecks = await Promise.all(users.map(async (user) => {
            let passes = true;
            if (hasPastSanctions) {
              passes = passes && await userHasPastSanctions(user.uid);
            }
            if (currentlySanctioned) {
              passes = passes && await isUserCurrentlySanctioned(user.uid);
            }
            return { user, passes };
          }));
          users = sanctionChecks.filter(({ passes }) => passes).map(({ user }) => user);
        }
        filteredUsers = users;
        if (!hasLoadedOnce) {
          const hasData = await hasAnyUsers();
          if (hasData) {
            hasLoadedOnce = true;
          }
        }
        updatePaginationContext();
      } catch (e) {
        error = e instanceof Error ? e.message : "Failed to load users";
        console.error("Error loading users:", e);
      } finally {
        isLoadingUsers = false;
      }
    }
    async function handleUserUpdated(_updatedUser) {
      editingUserId = null;
      await loadUsers();
    }
    function cancelEditUser() {
      editingUserId = null;
    }
    function handleUserEditingChange(editing) {
      const wasEditing = isUserEditing;
      isUserEditing = editing;
      if (wasEditing && !editing) {
        scheduleDisplayRefresh();
      }
    }
    function scheduleDisplayRefresh() {
      if (isUserEditing) {
        return;
      }
      if (displayRefreshTimer) {
        return;
      }
      displayRefreshTimer = setTimeout(
        async () => {
          displayRefreshTimer = void 0;
          await loadUsers();
        },
        100
      );
    }
    function handleCountryChange(e) {
      const target = e.target;
      selectedCountry = target.value;
      currentPage = 1;
      updateDisplayContext();
      loadUsers();
    }
    function updateDisplayContext() {
      const country = selectedCountry !== "all" ? selectedCountry : void 0;
      const roles = selectedRoles.length > 0 ? selectedRoles : void 0;
      const search = searchQuery.trim() || void 0;
      displayContext.setFilters(country, roles, search, filterHasPastSanctions, filterCurrentlySanctioned);
    }
    function updatePaginationContext() {
      const start = (currentPage - 1) * pageSize;
      const end = start + pageSize;
      const visibleUsers = filteredUsers.slice(start, end);
      displayContext.setPagination(currentPage, pageSize, visibleUsers);
    }
    $$renderer2.push(`<div class="p-4 sm:p-8"><div class="max-w-6xl mx-auto"><div class="mb-8"><div class="flex items-center justify-between mb-4"><h1 class="text-3xl font-light text-crimson-500">Users</h1> <div class="flex items-center gap-3"><button id="new-user-button"${attr(
      "disabled",
      // Initial load, SSE connection, and online/offline listeners
      // This effect should only run on mount - use untrack to avoid re-running on filter changes
      // Use untrack to prevent filter state from becoming dependencies
      // These calls are for initialization only, not reactive updates
      // Connect to SSE stream
      // Listen for sync events
      // SSE connected
      // Historical sync complete - stop showing syncing spinner
      // Refresh display to show any final data
      // Stop showing syncing on error
      // Connection lost - stop syncing state to avoid stuck spinner
      // Clear any pending timers
      !isOnline2,
      true
    )} class="px-4 py-2 text-sm font-medium text-bone-100 bg-emerald-700 hover:bg-emerald-600 disabled:bg-ash-700 rounded-lg transition-colors duration-200 shadow-md hover:shadow-lg disabled:cursor-not-allowed">${escape_html("+ New User")}</button> <button id="refresh-button"${attr("disabled", !isOnline2, true)} class="px-4 py-2 text-sm font-medium text-bone-100 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 rounded-lg transition-colors duration-200 shadow-md hover:shadow-lg disabled:cursor-not-allowed">Refresh</button></div></div> <div class="mb-4"><div class="bg-dusk-950 rounded-lg shadow p-4 mb-4 border border-ash-800"><div class="flex flex-wrap gap-4"><div class="flex-1 min-w-[200px]"><label for="name-search" class="block text-sm font-medium text-ash-400 mb-1">Search</label> <input id="name-search" type="text"${attr("value", searchQuery)} placeholder="Search by name or VEKN ID..." class="w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200 placeholder:text-ash-600"/></div> <div class="flex-1 min-w-[200px]"><label for="country-filter" class="block text-sm font-medium text-ash-400 mb-1">Country</label> `);
    $$renderer2.select(
      {
        id: "country-filter",
        onchange: handleCountryChange,
        value: selectedCountry,
        class: "w-full px-3 py-2 border border-ash-600 rounded-lg bg-dusk-950 text-ash-200"
      },
      ($$renderer3) => {
        $$renderer3.option({ value: "all" }, ($$renderer4) => {
          $$renderer4.push(`All Countries`);
        });
        $$renderer3.push(`<!--[-->`);
        const each_array = ensure_array_like(Object.entries(countries));
        for (let $$index = 0, $$length = each_array.length; $$index < $$length; $$index++) {
          let [code, country] = each_array[$$index];
          $$renderer3.option({ value: code }, ($$renderer4) => {
            $$renderer4.push(`${escape_html(country.name)} ${escape_html(getCountryFlag(code))}`);
          });
        }
        $$renderer3.push(`<!--]-->`);
      }
    );
    $$renderer2.push(`</div></div> <div class="mt-4"><div class="block text-sm font-medium text-ash-400 mb-2">Roles</div> <div class="flex flex-wrap gap-2"><!--[-->`);
    const each_array_1 = ensure_array_like(availableRoles);
    for (let $$index_1 = 0, $$length = each_array_1.length; $$index_1 < $$length; $$index_1++) {
      let role = each_array_1[$$index_1];
      $$renderer2.push(`<button${attr_class(`px-3 py-1 rounded text-sm font-medium transition-colors ${stringify(selectedRoles.includes(role) ? getRoleClasses(role) : "bg-ash-800 text-ash-400 hover:bg-ash-700")}`)}>${escape_html(role)}</button>`);
    }
    $$renderer2.push(`<!--]--></div></div> <div class="mt-4"><div class="block text-sm font-medium text-ash-400 mb-2">Sanctions</div> <div class="flex flex-wrap gap-2"><button${attr_class(`px-3 py-1 rounded text-sm font-medium transition-colors ${stringify("bg-ash-800 text-ash-400 hover:bg-ash-700")}`)}>Sanctioned</button> <button${attr_class(`px-3 py-1 rounded text-sm font-medium transition-colors ${stringify("bg-ash-800 text-ash-400 hover:bg-ash-700")}`)}>Active sanction</button></div></div></div></div></div> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (error) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div class="bg-crimson-900/20 border border-crimson-800 rounded-lg p-4 mb-6"><p class="text-crimson-300">${escape_html(error)}</p></div>`);
    } else {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (filteredUsers.length > 0) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div id="users-list-container" class="bg-dusk-950 rounded-lg shadow overflow-hidden border border-ash-800"><div id="users-table-header" class="hidden sm:grid sm:grid-cols-12 gap-4 px-6 py-3 bg-ash-900 text-sm font-medium text-ash-300 border-b border-ash-700"><div id="header-name" class="col-span-3">Name</div> <div id="header-vekn-id" class="col-span-2">VEKN ID</div> <div id="header-country" class="col-span-2">Country</div> <div id="header-roles" class="col-span-5">Roles</div></div> <div id="users-rows-container" class="divide-y divide-ash-800"><!--[-->`);
      const each_array_2 = ensure_array_like(paginatedUsers());
      for (let $$index_4 = 0, $$length = each_array_2.length; $$index_4 < $$length; $$index_4++) {
        let user = each_array_2[$$index_4];
        if (editingUserId === user.uid) {
          $$renderer2.push("<!--[-->");
          $$renderer2.push(`<div class="px-6 py-4">`);
          User($$renderer2, {
            user,
            mode: "edit",
            inline: true,
            showManagement: isOnline2,
            onupdated: handleUserUpdated,
            oncancel: cancelEditUser
          });
          $$renderer2.push(`<!----></div>`);
        } else {
          $$renderer2.push("<!--[!-->");
          if (expandedUserId === user.uid) {
            $$renderer2.push("<!--[-->");
            $$renderer2.push(`<div class="px-6 py-4 cursor-pointer" role="button" tabindex="0">`);
            User($$renderer2, {
              user,
              mode: "view",
              inline: true,
              editable: isOnline2,
              showManagement: isOnline2,
              onupdated: handleUserUpdated,
              oneditingchange: handleUserEditingChange
            });
            $$renderer2.push(`<!----></div>`);
          } else {
            $$renderer2.push("<!--[!-->");
            $$renderer2.push(`<div class="user-row px-6 py-4 hover:bg-ash-900/50 transition-colors cursor-pointer" role="button" tabindex="0"><div class="sm:hidden space-y-2"><div class="flex items-start justify-between"><div><div class="user-name font-semibold text-bone-100">${escape_html(user.name)} `);
            if (user.nickname) {
              $$renderer2.push("<!--[-->");
              $$renderer2.push(`<span class="text-sm text-ash-500">(${escape_html(user.nickname)})</span>`);
            } else {
              $$renderer2.push("<!--[!-->");
            }
            $$renderer2.push(`<!--]--></div> `);
            if (user.vekn_id) {
              $$renderer2.push("<!--[-->");
              $$renderer2.push(`<div class="text-sm text-ash-400 mt-1">VEKN: ${escape_html(user.vekn_id)}</div>`);
            } else {
              $$renderer2.push("<!--[!-->");
            }
            $$renderer2.push(`<!--]--> <div class="text-sm text-ash-400">${escape_html(user.country ? `${getCountryFlag(user.country)} ${countries[user.country]?.name || user.country}` : "N/A")}</div></div></div> `);
            if (user.roles.length > 0) {
              $$renderer2.push("<!--[-->");
              $$renderer2.push(`<div class="flex flex-wrap gap-1"><!--[-->`);
              const each_array_3 = ensure_array_like(user.roles);
              for (let $$index_2 = 0, $$length2 = each_array_3.length; $$index_2 < $$length2; $$index_2++) {
                let role = each_array_3[$$index_2];
                $$renderer2.push(`<span${attr_class(`px-2 py-1 rounded text-xs font-medium ${stringify(getRoleClasses(role))}`)}>${escape_html(role)}</span>`);
              }
              $$renderer2.push(`<!--]--></div>`);
            } else {
              $$renderer2.push("<!--[!-->");
            }
            $$renderer2.push(`<!--]--></div> <div class="hidden sm:grid sm:grid-cols-12 gap-4 items-center"><div class="col-span-3"><div class="user-name font-semibold text-bone-100">${escape_html(user.name)}</div> `);
            if (user.nickname) {
              $$renderer2.push("<!--[-->");
              $$renderer2.push(`<div class="text-sm text-ash-500">${escape_html(user.nickname)}</div>`);
            } else {
              $$renderer2.push("<!--[!-->");
            }
            $$renderer2.push(`<!--]--></div> <div class="col-span-2 text-sm text-ash-400">${escape_html(user.vekn_id || "—")}</div> <div class="col-span-2 text-sm text-ash-400">${escape_html(user.country ? `${getCountryFlag(user.country)} ${countries[user.country]?.name || user.country}` : "N/A")}</div> <div class="col-span-5">`);
            if (user.roles.length > 0) {
              $$renderer2.push("<!--[-->");
              $$renderer2.push(`<div class="flex flex-wrap gap-1"><!--[-->`);
              const each_array_4 = ensure_array_like(user.roles);
              for (let $$index_3 = 0, $$length2 = each_array_4.length; $$index_3 < $$length2; $$index_3++) {
                let role = each_array_4[$$index_3];
                $$renderer2.push(`<span${attr_class(`px-2 py-1 rounded text-xs font-medium ${stringify(getRoleClasses(role))}`)}>${escape_html(role)}</span>`);
              }
              $$renderer2.push(`<!--]--></div>`);
            } else {
              $$renderer2.push("<!--[!-->");
              $$renderer2.push(`<span class="text-sm text-ash-600">—</span>`);
            }
            $$renderer2.push(`<!--]--></div></div></div>`);
          }
          $$renderer2.push(`<!--]-->`);
        }
        $$renderer2.push(`<!--]-->`);
      }
      $$renderer2.push(`<!--]--></div></div> `);
      if (totalPages > 1) {
        $$renderer2.push("<!--[-->");
        $$renderer2.push(`<div class="mt-6 flex items-center justify-between"><div class="text-sm text-ash-400">Showing ${escape_html((currentPage - 1) * pageSize + 1)} to ${escape_html(Math.min(currentPage * pageSize, filteredUsers.length))} of ${escape_html(filteredUsers.length)} user${escape_html(filteredUsers.length !== 1 ? "s" : "")}</div> <div class="flex items-center gap-2"><button${attr("disabled", currentPage === 1, true)} class="px-3 py-1 text-sm font-medium text-ash-300 bg-dusk-950 border border-ash-600 rounded hover:bg-ash-800 disabled:opacity-50 disabled:cursor-not-allowed">Previous</button> <span class="text-sm text-ash-400">Page ${escape_html(currentPage)} of ${escape_html(totalPages)}</span> <button${attr("disabled", currentPage === totalPages, true)} class="px-3 py-1 text-sm font-medium text-ash-300 bg-dusk-950 border border-ash-600 rounded hover:bg-ash-800 disabled:opacity-50 disabled:cursor-not-allowed">Next</button></div></div>`);
      } else {
        $$renderer2.push("<!--[!-->");
        $$renderer2.push(`<div class="mt-6 text-center text-sm text-ash-400">Showing ${escape_html(filteredUsers.length)} user${escape_html(filteredUsers.length !== 1 ? "s" : "")}</div>`);
      }
      $$renderer2.push(`<!--]-->`);
    } else {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    if (!error && filteredUsers.length === 0) {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div class="text-center py-12">`);
      {
        $$renderer2.push("<!--[-->");
        $$renderer2.push(`<div class="text-ash-500 mb-4">`);
        Icon($$renderer2, {
          icon: "lucide:refresh-cw",
          class: "mx-auto h-12 w-12 animate-spin"
        });
        $$renderer2.push(`<!----></div> <h3 class="text-lg font-medium text-bone-100 mb-2">Syncing...</h3> <p class="text-ash-400">Loading users from server.</p>`);
      }
      $$renderer2.push(`<!--]--></div>`);
    } else {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--></div></div>`);
  });
}
function _page($$renderer) {
  head("9fk07v", $$renderer, ($$renderer2) => {
    $$renderer2.title(($$renderer3) => {
      $$renderer3.push(`<title>Users - Archon</title>`);
    });
  });
  UserList($$renderer);
}
export {
  _page as default
};
//# sourceMappingURL=_page.svelte.js.map
