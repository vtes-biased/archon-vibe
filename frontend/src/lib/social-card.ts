/**
 * Canvas-based PNG generation for social media sharing of tournament results.
 * Produces a 1080x1350 (4:5) dark card suitable for all social platforms.
 */
import type { Tournament } from "$lib/types";
import type { StandingEntry, PlayerInfoMap } from "$lib/tournament-utils";
import { seatDisplay } from "$lib/tournament-utils";
import { formatScore } from "$lib/utils";
import { getCountry } from "$lib/geonames";

// Colors from app.css
const BG = "#1C1A1E";
const TEXT = "#FAF8F4";
const CRIMSON = "#DC143C";
const MUTED = "#9A938C";
const DIM = "#7D756E";
const BORDER = "#4A4642";
const WINNER_BG = "rgba(220, 20, 60, 0.08)";
const FONT = "system-ui, -apple-system, sans-serif";

const W = 1080;
const H = 1350;
// Banners are 1.91:1 (1200×630), so at full width the whole image is ~567px tall
// and shown uncropped. The cap only bites on an unusually tall source.
const BANNER_MAX_H = 600;

/**
 * Load the tournament banner for compositing. crossOrigin='anonymous' keeps the
 * canvas untainted so toBlob() can't throw SecurityError (banner is same-origin
 * /api/tournaments/{uid}/banner, but be defensive). Resolves null when there's
 * no banner or it fails to load — the card then renders bannerless, never blocked.
 */
function loadBanner(tournament: Tournament): Promise<HTMLImageElement | null> {
  const src = tournament.banner_path;
  if (!src) return Promise.resolve(null);
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    // A hung request (stalled SW/flaky mobile) fires neither event; cap the wait
    // so the share degrades to the bannerless card instead of spinning forever.
    setTimeout(() => resolve(null), 4000);
    img.src = src;
  });
}

/**
 * Draw the full banner (no crop) as a header band and return the band height.
 * At full width the whole image is shown; only an unusually tall source hits
 * BANNER_MAX_H, in which case it's shrunk to fit and centered (letterboxed on
 * the BG) — width gives way so height is never cropped.
 */
function drawBanner(ctx: CanvasRenderingContext2D, img: HTMLImageElement): number {
  const fullH = Math.round((W * img.height) / img.width);
  if (fullH <= BANNER_MAX_H) {
    ctx.drawImage(img, 0, 0, W, fullH);
    return fullH;
  }
  const dw = Math.round((BANNER_MAX_H * img.width) / img.height);
  ctx.drawImage(img, (W - dw) / 2, 0, dw, BANNER_MAX_H);
  return BANNER_MAX_H;
}

function drawTextTruncated(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  align: CanvasTextAlign = "left",
) {
  ctx.textAlign = align;
  if (ctx.measureText(text).width <= maxWidth) {
    ctx.fillText(text, x, y);
    return;
  }
  let truncated = text;
  while (truncated.length > 0 && ctx.measureText(truncated + "...").width > maxWidth) {
    truncated = truncated.slice(0, -1);
  }
  ctx.fillText(truncated + "...", x, y);
}

function formatDateLine(tournament: Tournament): string {
  const parts: string[] = [];
  if (tournament.start) {
    const d = new Date(tournament.start);
    parts.push(d.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" }));
  }
  const loc: string[] = [];
  if (tournament.country) {
    const c = getCountry(tournament.country);
    if (c) loc.push(c.name);
  }
  if (loc.length) parts.push(loc.join(", "));
  return parts.join(" \u00B7 ");
}

function formatTypeLine(tournament: Tournament): string {
  const parts: string[] = [];
  if (tournament.format) parts.push(tournament.format);
  if (tournament.rank) parts.push(tournament.rank);
  return parts.join(" \u00B7 ");
}

export async function generateResultsCard(
  tournament: Tournament,
  playerInfo: PlayerInfoMap,
  standings: StandingEntry[],
): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d")!;

  // Background
  ctx.fillStyle = BG;
  ctx.fillRect(0, 0, W, H);

  const pad = 60;
  let y: number;

  // Full uncropped banner header band when set; else the plain top crimson
  // accent. Either way content flows below.
  const banner = await loadBanner(tournament);
  if (banner) {
    const bandH = drawBanner(ctx, banner);
    ctx.fillStyle = CRIMSON;
    ctx.fillRect(0, bandH, W, 6); // crimson divider under the band
    y = bandH + 60;
  } else {
    ctx.fillStyle = CRIMSON;
    ctx.fillRect(0, 0, W, 6);
    y = 70;
  }

  // Tournament name
  ctx.fillStyle = TEXT;
  ctx.font = `bold 48px ${FONT}`;
  drawTextTruncated(ctx, tournament.name, W / 2, y, W - pad * 2, "center");
  y += 50;

  // Date + location
  const dateLine = formatDateLine(tournament);
  if (dateLine) {
    ctx.fillStyle = MUTED;
    ctx.font = `24px ${FONT}`;
    drawTextTruncated(ctx, dateLine, W / 2, y, W - pad * 2, "center");
    y += 36;
  }

  // Format / rank
  const typeLine = formatTypeLine(tournament);
  if (typeLine) {
    ctx.fillStyle = DIM;
    ctx.font = `20px ${FONT}`;
    drawTextTruncated(ctx, typeLine, W / 2, y, W - pad * 2, "center");
    y += 36;
  }

  // Divider
  y += 10;
  ctx.strokeStyle = BORDER;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad, y);
  ctx.lineTo(W - pad, y);
  ctx.stroke();
  y += 30;

  // Winner section
  const hasFinals = standings.some((e) => e.finals);
  if (tournament.winner) {
    const winnerH = 100;
    ctx.fillStyle = WINNER_BG;
    ctx.beginPath();
    ctx.roundRect(pad, y, W - pad * 2, winnerH, 12);
    ctx.fill();

    ctx.fillStyle = TEXT;
    ctx.font = `bold 36px ${FONT}`;
    const winnerName = seatDisplay(tournament.winner, playerInfo, tournament.online);
    drawTextTruncated(ctx, winnerName, pad + 24, y + 45, W - pad * 2 - 48, "left");

    // Winner score
    const winnerEntry = standings.find((e) => e.user_uid === tournament.winner);
    if (winnerEntry) {
      ctx.fillStyle = CRIMSON;
      ctx.font = `bold 24px ${FONT}`;
      const scoreStr = formatScore(winnerEntry.gw, winnerEntry.vp, winnerEntry.tp);
      ctx.textAlign = "left";
      ctx.fillText(scoreStr, pad + 24, y + 78);
    }
    y += winnerH + 30;
  }

  // Top 5 standings table
  const top5 = standings.slice(0, 5);
  if (top5.length > 0) {
    // Header
    ctx.fillStyle = MUTED;
    ctx.font = `bold 20px ${FONT}`;
    const colRank = pad + 10;
    const colName = pad + 70;
    const colScore = W - pad - 10;
    const colFinals = hasFinals ? colScore - 180 : colScore;

    ctx.textAlign = "left";
    ctx.fillText("#", colRank, y);
    ctx.fillText("Player", colName, y);
    ctx.textAlign = "right";
    ctx.fillText("Score", hasFinals ? colFinals - 20 : colScore, y);
    if (hasFinals) ctx.fillText("Finals", colScore, y);
    y += 12;

    // Header line
    ctx.strokeStyle = BORDER;
    ctx.beginPath();
    ctx.moveTo(pad, y);
    ctx.lineTo(W - pad, y);
    ctx.stroke();
    y += 30;

    // Rows
    for (const entry of top5) {
      ctx.fillStyle = DIM;
      ctx.font = `20px ${FONT}`;
      ctx.textAlign = "left";
      ctx.fillText(String(entry.rank), colRank, y);

      ctx.fillStyle = TEXT;
      ctx.font = `22px ${FONT}`;
      const nameStr = seatDisplay(entry.user_uid, playerInfo, tournament.online);
      const nameMaxW = (hasFinals ? colFinals - 20 : colScore) - colName - 20;
      drawTextTruncated(ctx, nameStr, colName, y, nameMaxW, "left");

      ctx.fillStyle = MUTED;
      ctx.font = `20px ${FONT}`;
      ctx.textAlign = "right";
      ctx.fillText(formatScore(entry.gw, entry.vp, entry.tp), hasFinals ? colFinals - 20 : colScore, y);

      if (hasFinals && entry.finals) {
        ctx.fillText(entry.finals, colScore, y);
      }

      y += 44;

      // Row separator
      ctx.strokeStyle = BORDER;
      ctx.globalAlpha = 0.4;
      ctx.beginPath();
      ctx.moveTo(pad, y - 14);
      ctx.lineTo(W - pad, y - 14);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
  }

  // Footer area - push to bottom
  const footerY = H - 80;
  ctx.fillStyle = DIM;
  ctx.font = `20px ${FONT}`;
  ctx.textAlign = "left";
  const playerCount = tournament.players?.length ?? 0;
  if (playerCount > 0) {
    ctx.fillText(`${playerCount} players`, pad, footerY);
  }
  ctx.textAlign = "right";
  ctx.fillText("archon.vekn.net", W - pad, footerY);

  // Bottom crimson accent bar
  ctx.fillStyle = CRIMSON;
  ctx.fillRect(0, H - 6, W, 6);

  return new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Canvas toBlob failed"))),
      "image/png",
    );
  });
}
