<script lang="ts">
  import Icon from '@iconify/svelte';
  import * as m from '$lib/paraglide/messages.js';

  // Props
  interface Props {
    onSave: (blob: Blob) => Promise<void>;
    onCancel: () => void;
  }
  let { onSave, onCancel }: Props = $props();

  // State
  let fileInput: HTMLInputElement | null = $state(null);
  let canvas: HTMLCanvasElement | null = $state(null);
  let image: HTMLImageElement | null = $state(null);
  let saving = $state(false);

  // Transform state
  let scale = $state(1);
  let offsetX = $state(0);
  let offsetY = $state(0);

  // Dynamic scale limits (computed based on image)
  let minScale = $state(0.1);
  let maxScale = $state(3);

  // Drag state
  let isDragging = $state(false);
  let dragStartX = $state(0);
  let dragStartY = $state(0);
  let dragStartOffsetX = $state(0);
  let dragStartOffsetY = $state(0);

  // Constants
  const CANVAS_SIZE = 256;

  function focusOnMount(node: HTMLElement) {
    node.focus();
  }

  function handleFileSelect(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
      alert(m.avatar_select_image_file());
      return;
    }

    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new Image();
      img.onload = () => {
        image = img;
        // Reset transform
        offsetX = 0;
        offsetY = 0;

        // Compute scale limits based on image size
        const maxDim = Math.max(img.width, img.height);
        const minDim = Math.min(img.width, img.height);

        // Min scale: fit entire image (largest dimension) in canvas
        minScale = CANVAS_SIZE / maxDim;
        // Max scale: at least 3x the fit scale, or enough to show detail
        maxScale = Math.max(3, (CANVAS_SIZE / minDim) * 3);

        // Initial scale: fit smallest dimension to fill canvas
        scale = CANVAS_SIZE / minDim;

        drawCanvas();
      };
      img.src = e.target?.result as string;
    };
    reader.readAsDataURL(file);
  }

  function drawCanvas() {
    if (!canvas || !image) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Clear
    ctx.clearRect(0, 0, CANVAS_SIZE, CANVAS_SIZE);

    // Draw image centered with transform
    const scaledWidth = image.width * scale;
    const scaledHeight = image.height * scale;
    const x = (CANVAS_SIZE - scaledWidth) / 2 + offsetX;
    const y = (CANVAS_SIZE - scaledHeight) / 2 + offsetY;

    ctx.drawImage(image, x, y, scaledWidth, scaledHeight);
  }

  function handleZoom(event: Event) {
    scale = parseFloat((event.target as HTMLInputElement).value);
    drawCanvas();
  }

  function handleMouseDown(event: MouseEvent) {
    if (!image) return;
    isDragging = true;
    dragStartX = event.clientX;
    dragStartY = event.clientY;
    dragStartOffsetX = offsetX;
    dragStartOffsetY = offsetY;
  }

  function handleMouseMove(event: MouseEvent) {
    if (!isDragging) return;
    offsetX = dragStartOffsetX + (event.clientX - dragStartX);
    offsetY = dragStartOffsetY + (event.clientY - dragStartY);
    drawCanvas();
  }

  function handleMouseUp() {
    isDragging = false;
  }

  function handleTouchStart(event: TouchEvent) {
    const touch = event.touches[0];
    if (!image || !touch) return;
    isDragging = true;
    dragStartX = touch.clientX;
    dragStartY = touch.clientY;
    dragStartOffsetX = offsetX;
    dragStartOffsetY = offsetY;
  }

  function handleTouchMove(event: TouchEvent) {
    const touch = event.touches[0];
    if (!isDragging || !touch) return;
    event.preventDefault();
    offsetX = dragStartOffsetX + (touch.clientX - dragStartX);
    offsetY = dragStartOffsetY + (touch.clientY - dragStartY);
    drawCanvas();
  }

  function handleTouchEnd() {
    isDragging = false;
  }

  async function handleSave() {
    if (!canvas) return;
    saving = true;

    try {
      // Convert canvas to blob
      const blob = await new Promise<Blob>((resolve, reject) => {
        canvas!.toBlob(
          (b) => {
            if (b) resolve(b);
            else reject(new Error('Failed to create blob'));
          },
          'image/webp',
          0.85
        );
      });

      await onSave(blob);
    } catch (error) {
      console.error('Failed to save avatar:', error);
      alert(m.avatar_save_failed());
    } finally {
      saving = false;
    }
  }

  // Redraw when scale/offset changes
  $effect(() => {
    if (image) {
      drawCanvas();
    }
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
    aria-labelledby="avatar-modal-title"
    tabindex="-1"
    use:focusOnMount
    onkeydown={(e) => e.key === 'Escape' && onCancel()}
    class="bg-dusk-950 rounded-lg p-6 max-w-sm w-full"
  >
    <h2 id="avatar-modal-title" class="text-lg font-semibold text-bone-200 mb-4">{m.avatar_title()}</h2>

    {#if !image}
      <!-- File selection -->
      <div class="flex flex-col items-center gap-4">
        <button
          onclick={() => fileInput?.click()}
          class="w-32 h-32 rounded-full border-2 border-dashed border-ash-600 flex items-center justify-center hover:border-crimson-500 transition-colors"
        >
          <Icon icon="lucide:image-plus" class="w-12 h-12 text-ash-500" />
        </button>
        <p class="text-sm text-ash-400">{m.avatar_select_image()}</p>
        <input
          bind:this={fileInput}
          type="file"
          accept="image/*"
          class="hidden"
          onchange={handleFileSelect}
        />
      </div>
    {:else}
      <!-- Cropper -->
      <div class="flex flex-col items-center gap-4">
        <!-- Canvas with circular mask preview -->
        <div
          role="slider"
          aria-label={m.avatar_drag_reposition()}
          aria-valuemin="0"
          aria-valuemax="100"
          aria-valuenow={50}
          tabindex="0"
          class="relative cursor-move touch-none"
          onmousedown={handleMouseDown}
          onmousemove={handleMouseMove}
          onmouseup={handleMouseUp}
          onmouseleave={handleMouseUp}
          ontouchstart={handleTouchStart}
          ontouchmove={handleTouchMove}
          ontouchend={handleTouchEnd}
        >
          <canvas
            bind:this={canvas}
            width={CANVAS_SIZE}
            height={CANVAS_SIZE}
            class="rounded-full"
          ></canvas>
          <!-- Circular overlay to show crop area -->
          <div
            class="absolute inset-0 rounded-full ring-4 ring-crimson-500/50 pointer-events-none"
          ></div>
        </div>

        <!-- Zoom control -->
        <div class="w-full flex items-center gap-3">
          <Icon icon="lucide:zoom-out" class="w-5 h-5 text-ash-400" />
          <input
            type="range"
            min={minScale}
            max={maxScale}
            step={Math.max(0.01, (maxScale - minScale) / 100)}
            value={scale}
            oninput={handleZoom}
            class="flex-1 accent-crimson-500"
          />
          <Icon icon="lucide:zoom-in" class="w-5 h-5 text-ash-400" />
        </div>

        <p class="text-xs text-ash-500">{m.avatar_drag_reposition()}</p>
      </div>
    {/if}

    <!-- Actions -->
    <div class="flex gap-3 mt-6">
      <button
        onclick={onCancel}
        class="flex-1 px-4 py-2 rounded-lg border border-ash-600 text-ash-300 hover:bg-ash-800 transition-colors"
      >
        {m.common_cancel()}
      </button>
      {#if image}
        <button
          onclick={handleSave}
          disabled={saving}
          class="flex-1 px-4 py-2 rounded-lg bg-crimson-600 text-white hover:bg-crimson-500 transition-colors disabled:opacity-50"
        >
          {saving ? m.common_saving() : m.common_save()}
        </button>
      {/if}
    </div>
  </div>
</div>
