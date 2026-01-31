import { a3 as head, _ as attr_class, a1 as attr, $ as stringify } from "../../../chunks/index2.js";
import "@sveltejs/kit/internal";
import "../../../chunks/exports.js";
import "../../../chunks/utils.js";
import "@sveltejs/kit/internal/server";
import "../../../chunks/state.svelte.js";
import { i as isPasskeySupported, g as getAuthState } from "../../../chunks/auth.svelte.js";
import { I as Icon } from "../../../chunks/Icon.js";
function _page($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    const auth = getAuthState();
    const passkeySupported = isPasskeySupported();
    let email = "";
    let password = "";
    head("1x05zx6", $$renderer2, ($$renderer3) => {
      $$renderer3.title(($$renderer4) => {
        $$renderer4.push(`<title>Welcome - Archon</title>`);
      });
    });
    $$renderer2.push(`<div class="min-h-screen flex items-center justify-center p-4"><div class="w-full max-w-md"><div class="text-center mb-8"><h1 class="text-4xl font-light text-crimson-500 mb-2">Archon</h1> <p class="text-ash-400">VEKN Tournament Management</p></div> <div class="bg-dusk-950 rounded-lg shadow-lg p-8 border border-ash-800">`);
    {
      $$renderer2.push("<!--[-->");
      $$renderer2.push(`<div class="flex mb-6 bg-dusk-900 rounded-lg p-1"><button${attr_class(`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${stringify("bg-crimson-700 text-bone-100")}`)}>Login</button> <button${attr_class(`flex-1 py-2 px-4 rounded-md text-sm font-medium transition-colors ${stringify("text-ash-400 hover:text-ash-200")}`)}>Sign Up</button></div>`);
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]--> `);
    {
      $$renderer2.push("<!--[!-->");
      {
        $$renderer2.push("<!--[!-->");
        {
          $$renderer2.push("<!--[!-->");
          {
            $$renderer2.push("<!--[-->");
            $$renderer2.push(`<div class="space-y-4"><p class="text-ash-400 text-sm text-center mb-4">Welcome back! Sign in to your account.</p> <form class="space-y-4"><div><label for="login-email" class="block text-sm text-ash-400 mb-1">Email</label> <input type="email" id="login-email" name="email" autocomplete="username"${attr("value", email)} placeholder="you@example.com"${attr("disabled", auth.isLoading, true)} class="w-full px-4 py-3 bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500 focus:outline-none focus:border-crimson-600 disabled:opacity-50"/></div> <div><label for="login-password" class="block text-sm text-ash-400 mb-1">Password</label> <input type="password" id="login-password" name="password" autocomplete="current-password"${attr("value", password)} placeholder="Enter your password"${attr("disabled", auth.isLoading, true)} class="w-full px-4 py-3 bg-dusk-900 border border-ash-700 rounded-lg text-bone-100 placeholder-ash-500 focus:outline-none focus:border-crimson-600 disabled:opacity-50"/></div> <button type="submit"${attr("disabled", auth.isLoading, true)} class="w-full py-3 bg-crimson-700 hover:bg-crimson-600 disabled:bg-ash-700 disabled:opacity-50 text-bone-100 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:cursor-not-allowed">`);
            {
              $$renderer2.push("<!--[-->");
              Icon($$renderer2, { icon: "lucide:loader-2", class: "w-5 h-5 animate-spin" });
            }
            $$renderer2.push(`<!--]--> Sign In</button></form> <button class="w-full text-sm text-ash-400 hover:text-ash-200">Forgot password?</button> <div class="relative my-4"><div class="absolute inset-0 flex items-center"><div class="w-full border-t border-ash-700"></div></div> <div class="relative flex justify-center text-sm"><span class="px-2 bg-dusk-950 text-ash-500">or</span></div></div> `);
            if (passkeySupported) {
              $$renderer2.push("<!--[-->");
              $$renderer2.push(`<button${attr("disabled", auth.isLoading, true)} class="w-full py-3 bg-ash-800 hover:bg-ash-700 disabled:bg-ash-700 text-bone-100 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:cursor-not-allowed">`);
              Icon($$renderer2, { icon: "lucide:key-round", class: "w-5 h-5" });
              $$renderer2.push(`<!----> Sign in with Passkey</button>`);
            } else {
              $$renderer2.push("<!--[!-->");
            }
            $$renderer2.push(`<!--]--> <button${attr("disabled", auth.isLoading, true)} class="w-full py-3 bg-[#5865F2] hover:bg-[#4752C4] disabled:bg-ash-700 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2 disabled:cursor-not-allowed">`);
            Icon($$renderer2, { icon: "simple-icons:discord", class: "w-5 h-5" });
            $$renderer2.push(`<!----> Continue with Discord</button> `);
            if (!passkeySupported) {
              $$renderer2.push("<!--[-->");
              $$renderer2.push(`<p class="text-center text-sm text-ash-500">Passkeys are not supported in this browser.</p>`);
            } else {
              $$renderer2.push("<!--[!-->");
            }
            $$renderer2.push(`<!--]--></div>`);
          }
          $$renderer2.push(`<!--]-->`);
        }
        $$renderer2.push(`<!--]-->`);
      }
      $$renderer2.push(`<!--]-->`);
    }
    $$renderer2.push(`<!--]--></div></div></div>`);
  });
}
export {
  _page as default
};
//# sourceMappingURL=_page.svelte.js.map
