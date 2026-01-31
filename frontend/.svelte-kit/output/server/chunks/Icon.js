import { a6 as attributes } from "./index2.js";
import { b as ssr_context } from "./context.js";
import "clsx";
import { c as checkIconState, g as generateIcon } from "./functions.js";
function html(value) {
  var html2 = String(value ?? "");
  var open = "<!---->";
  return open + html2 + "<!---->";
}
function onDestroy(fn) {
  /** @type {SSRContext} */
  ssr_context.r.on_destroy(fn);
}
function Icon($$renderer, $$props) {
  $$renderer.component(($$renderer2) => {
    const iconState = {
      // Last icon name
      name: "",
      // Loading status
      loading: null,
      // Destroyed status
      destroyed: false
    };
    const { $$slots, $$events, ...props } = $$props;
    let iconData = (() => {
      return checkIconState(props.icon, iconState, loaded, props.onload);
    })();
    let data = (() => {
      const generatedData = iconData ? generateIcon(iconData.data, props) : null;
      if (generatedData && iconData.classes && props["class"] === void 0) {
        generatedData.attributes["class"] = (typeof props["class"] === "string" ? props["class"] + " " : "") + iconData.classes.join(" ");
      }
      return generatedData;
    })();
    function loaded() {
    }
    onDestroy(() => {
      iconState.destroyed = true;
      if (iconState.loading) {
        iconState.loading.abort();
        iconState.loading = null;
      }
    });
    if (data) {
      $$renderer2.push("<!--[-->");
      if (data.svg) {
        $$renderer2.push("<!--[-->");
        $$renderer2.push(`<svg${attributes({ ...data.attributes }, void 0, void 0, void 0, 3)}>${html(data.body)}</svg>`);
      } else {
        $$renderer2.push("<!--[!-->");
        $$renderer2.push(`<span${attributes({ ...data.attributes })}></span>`);
      }
      $$renderer2.push(`<!--]-->`);
    } else {
      $$renderer2.push("<!--[!-->");
    }
    $$renderer2.push(`<!--]-->`);
  });
}
export {
  Icon as I
};
//# sourceMappingURL=Icon.js.map
