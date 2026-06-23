<script lang="ts">
  import Button from '$lib/components/Button.svelte';
  import { ImagePlus, ZoomOut, ZoomIn } from "@lucide/svelte";
  import * as m from '$lib/paraglide/messages.js';
  import { showToast } from '$lib/stores/toast.svelte';

  interface Props {
    onSave: (blob: Blob) => Promise<void>;
    onCancel: () => void;
  }
  let { onSave, onCancel }: Props = $props();

  let fileInput: HTMLInputElement | null = $state(null);
  let canvas: HTMLCanvasElement | null = $state(null);
  // Square "what mobile / WhatsApp crops to" preview: the centered square column
  // of the 1.91:1 crop (see drawCanvas — same transform, narrower frame).
  let squareCanvas: HTMLCanvasElement | null = $state(null);
  let image: HTMLImageElement | null = $state(null);
  let saving = $state(false);

  // Transform (expressed in CROP-canvas pixels)
  let scale = $state(1);
  let offsetX = $state(0);
  let offsetY = $state(0);
  let minScale = $state(0.1);
  let maxScale = $state(3);

  let isDragging = $state(false);
  let dragStartX = $state(0);
  let dragStartY = $state(0);
  let dragStartOffsetX = $state(0);
  let dragStartOffsetY = $state(0);

  // Crop preview is 400×210; export at 3× → 1200×630 (the og:image size, ≈1.91:1).
  const CROP_W = 400;
  const CROP_H = 210;
  const OUT_SCALE = 3;
  // Square preview side = crop height: painting the same transform into a square
  // frame yields exactly the centered square the crop would be center-cropped to.
  const SQUARE = CROP_H;

  function focusOnMount(node: HTMLElement) {
    const input = node.querySelector<HTMLElement>("input:not(.hidden):not([type=hidden]), textarea, select");
    (input ?? node).focus();
  }

  function handleFileSelect(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      showToast({ type: 'error', message: m.avatar_select_image_file() });
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      // Some phone formats (e.g. HEIC) can't always decode in a canvas — surface
      // a clear message instead of a silent dead cropper.
      img.onerror = () => showToast({ type: 'error', message: m.banner_save_failed() });
      img.onload = () => {
        image = img;
        offsetX = 0;
        offsetY = 0;
        // Floor zoom at "cover" so the 1.91:1 frame is always fully filled —
        // no transparent gaps can sneak into the banner. Pan/zoom in from there.
        const coverScale = Math.max(CROP_W / img.width, CROP_H / img.height);
        minScale = coverScale;
        maxScale = coverScale * 3;
        scale = coverScale;
        drawCanvas();
      };
      img.src = e.target?.result as string;
    };
    reader.readAsDataURL(file);
  }

  // Draw the current transform onto an arbitrary ctx sized w×h (k scales the
  // CROP-space transform up for the export canvas).
  function paint(ctx: CanvasRenderingContext2D, w: number, h: number, k: number) {
    if (!image) return;
    ctx.clearRect(0, 0, w, h);
    const sw = image.width * scale * k;
    const sh = image.height * scale * k;
    const x = (w - sw) / 2 + offsetX * k;
    const y = (h - sh) / 2 + offsetY * k;
    ctx.drawImage(image, x, y, sw, sh);
  }

  // Keep the (already cover-or-larger) image fully covering the frame: limit the
  // pan so neither edge can slide inside the crop box and reveal a gap.
  function clampOffsets() {
    if (!image) return;
    const maxX = Math.max(0, (image.width * scale - CROP_W) / 2);
    const maxY = Math.max(0, (image.height * scale - CROP_H) / 2);
    offsetX = Math.min(maxX, Math.max(-maxX, offsetX));
    offsetY = Math.min(maxY, Math.max(-maxY, offsetY));
  }

  function drawCanvas() {
    const ctx = canvas?.getContext('2d');
    if (ctx) paint(ctx, CROP_W, CROP_H, 1);
    const sctx = squareCanvas?.getContext('2d');
    if (sctx) paint(sctx, SQUARE, SQUARE, 1);
  }

  function handleZoom(event: Event) {
    scale = parseFloat((event.target as HTMLInputElement).value);
    clampOffsets();
    drawCanvas();
  }

  // Pointer deltas are in CSS px; the canvas may be CSS-scaled on narrow
  // screens, so convert to CROP-canvas px before applying to the offset.
  function displayScale(): number {
    if (!canvas) return 1;
    const rect = canvas.getBoundingClientRect();
    return rect.width ? CROP_W / rect.width : 1;
  }

  function startDrag(clientX: number, clientY: number) {
    if (!image) return;
    isDragging = true;
    dragStartX = clientX;
    dragStartY = clientY;
    dragStartOffsetX = offsetX;
    dragStartOffsetY = offsetY;
  }
  function moveDrag(clientX: number, clientY: number) {
    if (!isDragging) return;
    const k = displayScale();
    offsetX = dragStartOffsetX + (clientX - dragStartX) * k;
    offsetY = dragStartOffsetY + (clientY - dragStartY) * k;
    clampOffsets();
    drawCanvas();
  }

  function handleMouseDown(e: MouseEvent) { startDrag(e.clientX, e.clientY); }
  function handleMouseMove(e: MouseEvent) { moveDrag(e.clientX, e.clientY); }
  function handleMouseUp() { isDragging = false; }
  function handleTouchStart(e: TouchEvent) {
    const t = e.touches[0];
    if (t) startDrag(t.clientX, t.clientY);
  }
  function handleTouchMove(e: TouchEvent) {
    const t = e.touches[0];
    if (!isDragging || !t) return;
    e.preventDefault();
    moveDrag(t.clientX, t.clientY);
  }
  function handleTouchEnd() { isDragging = false; }

  async function handleSave() {
    if (!image) return;
    saving = true;
    // Local crop → blob. A failure here is ours to report (the upload layer
    // toasts its own errors), so keep the two stages' error handling separate.
    let blob: Blob;
    try {
      const out = document.createElement('canvas');
      out.width = CROP_W * OUT_SCALE;
      out.height = CROP_H * OUT_SCALE;
      const ctx = out.getContext('2d');
      if (!ctx) throw new Error('no 2d context');
      paint(ctx, out.width, out.height, OUT_SCALE);
      blob = await new Promise<Blob>((resolve, reject) => {
        out.toBlob((b) => (b ? resolve(b) : reject(new Error('toBlob failed'))), 'image/webp', 0.85);
      });
    } catch (error) {
      console.error('Failed to render banner:', error);
      showToast({ type: 'error', message: m.banner_save_failed() });
      saving = false;
      return;
    }
    try {
      await onSave(blob); // upload; errors already surfaced by the api layer
    } catch (error) {
      console.error('Failed to upload banner:', error); // keep modal open to retry
    } finally {
      saving = false;
    }
  }

  $effect(() => {
    if (image) drawCanvas();
  });
</script>

<div
  role="presentation"
  class="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4"
  onclick={(e) => e.target === e.currentTarget && onCancel()}
>
  <div
    role="dialog"
    aria-modal="true"
    aria-labelledby="banner-modal-title"
    tabindex="-1"
    use:focusOnMount
    onkeydown={(e) => e.key === 'Escape' && onCancel()}
    class="bg-surface-card rounded-lg p-6 max-w-lg w-full"
  >
    <h2 id="banner-modal-title" class="text-lg font-semibold text-ink-strong mb-1">{m.banner_title()}</h2>
    <p class="text-xs text-ink-faint mb-4">{m.banner_dimensions_hint()}</p>

    {#if !image}
      <div class="flex flex-col items-center gap-4">
        <button
          onclick={() => fileInput?.click()}
          class="w-full aspect-[1200/630] rounded-lg border-2 border-dashed border-line-strong flex items-center justify-center hover:border-accent transition-colors"
        >
          <ImagePlus class="w-12 h-12 text-ink-faint" />
        </button>
        <p class="text-sm text-ink-muted">{m.avatar_select_image()}</p>
        <input bind:this={fileInput} type="file" accept="image/*" class="hidden" onchange={handleFileSelect} />
      </div>
    {:else}
      <div class="flex flex-col items-center gap-4">
        <div
          role="slider"
          aria-label={m.avatar_drag_reposition()}
          aria-valuemin="0"
          aria-valuemax="100"
          aria-valuenow={50}
          tabindex="0"
          class="relative cursor-move touch-none w-full"
          onmousedown={handleMouseDown}
          onmousemove={handleMouseMove}
          onmouseup={handleMouseUp}
          onmouseleave={handleMouseUp}
          ontouchstart={handleTouchStart}
          ontouchmove={handleTouchMove}
          ontouchend={handleTouchEnd}
        >
          <!-- The whole canvas IS the crop — frame exactly equals the output. -->
          <canvas bind:this={canvas} width={CROP_W} height={CROP_H} class="w-full h-auto rounded-lg bg-surface-muted"></canvas>
          <!-- Safe zone (~1080×565, centered): edges/corners get cropped or rounded
               on square/mobile placements, so keep title + key art inside it. -->
          <div class="pointer-events-none absolute inset-0 rounded-lg overflow-hidden">
            <div class="absolute inset-[5%] border border-dashed border-white/70 rounded"></div>
          </div>
        </div>

        <div class="w-full flex items-center gap-3">
          <ZoomOut class="w-5 h-5 text-ink-muted" />
          <input
            type="range"
            min={minScale}
            max={maxScale}
            step={Math.max(0.01, (maxScale - minScale) / 100)}
            value={scale}
            oninput={handleZoom}
            class="flex-1 accent-accent"
          />
          <ZoomIn class="w-5 h-5 text-ink-muted" />
        </div>

        <div class="w-full flex items-center gap-3">
          <canvas
            bind:this={squareCanvas}
            width={SQUARE}
            height={SQUARE}
            class="w-16 h-16 rounded bg-surface-muted shrink-0"
          ></canvas>
          <p class="text-xs text-ink-faint">{m.banner_mobile_preview_hint()}</p>
        </div>

        <p class="text-xs text-ink-faint">{m.avatar_drag_reposition()}</p>
      </div>
    {/if}

    <div class="flex gap-3 mt-6">
      <Button variant="ghost" size="lg" class="flex-1" onclick={onCancel}>
        {m.common_cancel()}
      </Button>
      {#if image}
        <Button variant="primary" size="lg" class="flex-1" loading={saving} onclick={handleSave}>
          {saving ? m.common_saving() : m.common_save()}
        </Button>
      {/if}
    </div>
  </div>
</div>
