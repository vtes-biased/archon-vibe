<script lang="ts">
  import { onMount } from "svelte";
  import { replaceState } from "$app/navigation";
  import { showToast } from "$lib/stores/toast.svelte";
  import type { TocEntry } from "$lib/help-docs";

  interface Props {
    html: string;
    tocEntries: TocEntry[];
    onActiveHeadingChange: (id: string) => void;
  }
  let { html, tocEntries, onActiveHeadingChange }: Props = $props();

  let articleEl: HTMLElement | undefined = $state();

  onMount(() => {
    if (!articleEl) return;

    // Scroll to hash on mount
    if (window.location.hash) {
      const target = document.getElementById(window.location.hash.slice(1));
      if (target) {
        setTimeout(() => target.scrollIntoView(), 100);
      }
    }

    // IntersectionObserver to track active heading
    const headingIds = tocEntries.map(e => e.id);
    const headingEls = headingIds
      .map(id => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null);

    if (headingEls.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        // Find the topmost visible heading
        for (const entry of entries) {
          if (entry.isIntersecting) {
            onActiveHeadingChange(entry.target.id);
            replaceState(`#${entry.target.id}`, {});
            break;
          }
        }
      },
      { rootMargin: "-10% 0px -80% 0px", threshold: 0 }
    );

    for (const el of headingEls) observer.observe(el);

    // Classify images by aspect ratio and size for appropriate rendering
    for (const img of articleEl.querySelectorAll<HTMLImageElement>("img.doc-img")) {
      const classify = () => {
        const { naturalWidth: w, naturalHeight: h } = img;
        const ratio = w / h;
        if (ratio > 2 && h > 300) img.classList.add("doc-img-wide");    // wide panoramic diagrams → full width
        else if (w > 800 && h > 1200) img.classList.add("doc-img-wide"); // tall full-page diagrams
        else if (w <= 250 && h <= 250) img.classList.add("doc-img-icon"); // small icons → tiny
        else if (ratio > 0.85 && ratio < 1.2 && w <= 700) img.classList.add("doc-img-medium"); // square-ish photos
      };
      if (img.complete) classify();
      else img.addEventListener("load", classify, { once: true });
    }

    // Click delegation for anchor links
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      const anchor = target.closest(".anchor-link");
      if (anchor instanceof HTMLAnchorElement) {
        e.preventDefault();
        const url = new URL(anchor.href, window.location.href);
        navigator.clipboard.writeText(url.toString()).then(() => {
          showToast({ type: "success", message: "Link copied" });
        });
      }
    };
    articleEl.addEventListener("click", handleClick);

    return () => {
      observer.disconnect();
      articleEl?.removeEventListener("click", handleClick);
    };
  });
</script>

<article
  bind:this={articleEl}
  class="doc-prose prose max-w-none"
>
  {@html html}
</article>
