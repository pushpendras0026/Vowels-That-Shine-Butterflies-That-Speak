// plot.js — tiny dependency-free canvas plotting helpers shared by the Story / Theory pages.
// Pure drawing; no physics here (physics lives only in physics.js).

/** Resize a canvas to its CSS box at devicePixelRatio; returns {ctx, w, h} in CSS pixels. */
export function fitCanvas(cv) {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.max(50, cv.clientWidth || 300);
  const h = Math.max(50, cv.clientHeight || 200);
  const W = Math.round(w * dpr), H = Math.round(h * dpr);
  if (cv.width !== W || cv.height !== H) { cv.width = W; cv.height = H; }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h };
}

function niceStep(span, target) {
  const raw = span / Math.max(1, target);
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const m = raw / p;
  return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p;
}

/**
 * Draw axes + grid in box {x,y,w,h}. Returns mapping functions X(x), Y(y) and the box.
 * opts: xmin,xmax,ymin,ymax,xlabel,ylabel,fmtX,fmtY,xticks(target count),yticks
 */
export function axes(ctx, box, o) {
  const { x, y, w, h } = box;
  const X = (v) => x + (v - o.xmin) / (o.xmax - o.xmin) * w;
  const Y = (v) => y + h - (v - o.ymin) / (o.ymax - o.ymin) * h;
  ctx.save();
  ctx.font = "11px Segoe UI, system-ui, sans-serif";
  ctx.strokeStyle = "rgba(255,255,255,0.07)";
  ctx.fillStyle = "#9aa1b5";
  ctx.lineWidth = 1;
  const fx = o.fmtX || ((v) => +v.toFixed(6) + "");
  const fy = o.fmtY || ((v) => +v.toFixed(6) + "");
  const sx = niceStep(o.xmax - o.xmin, o.xticks || 6);
  ctx.textAlign = "center"; ctx.textBaseline = "top";
  for (let v = Math.ceil(o.xmin / sx) * sx; v <= o.xmax + 1e-9 * sx; v += sx) {
    const px = Math.round(X(v)) + 0.5;
    ctx.beginPath(); ctx.moveTo(px, y); ctx.lineTo(px, y + h); ctx.stroke();
    ctx.fillText(fx(v), px, y + h + 4);
  }
  const sy = niceStep(o.ymax - o.ymin, o.yticks || 4);
  ctx.textAlign = "right"; ctx.textBaseline = "middle";
  for (let v = Math.ceil(o.ymin / sy) * sy; v <= o.ymax + 1e-9 * sy; v += sy) {
    const py = Math.round(Y(v)) + 0.5;
    ctx.beginPath(); ctx.moveTo(x, py); ctx.lineTo(x + w, py); ctx.stroke();
    ctx.fillText(fy(v), x - 5, py);
  }
  ctx.strokeStyle = "rgba(255,255,255,0.25)";
  ctx.strokeRect(x + 0.5, y + 0.5, w, h);
  if (o.xlabel) { ctx.textAlign = "center"; ctx.textBaseline = "bottom"; ctx.fillText(o.xlabel, x + w / 2, y + h + 34); }
  if (o.ylabel) {
    ctx.translate(x - 40, y + h / 2); ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillText(o.ylabel, 0, 0);
  }
  ctx.restore();
  return { X, Y, box };
}

/** Polyline of (xs[i], ys[i]) through the axis mapping, clipped to the box. */
export function line(ctx, ax, xs, ys, { color = "#8f7bff", width = 2, dash = null, alpha = 1 } = {}) {
  const { x, y, w, h } = ax.box;
  ctx.save();
  ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineJoin = "round";
  if (dash) ctx.setLineDash(dash);
  ctx.beginPath();
  for (let i = 0; i < xs.length; i++) {
    const px = ax.X(xs[i]), py = ax.Y(ys[i]);
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  }
  ctx.stroke();
  ctx.restore();
}

/** Approximate sRGB colour of a monochromatic wavelength (ARTISTIC rendering of the spectrum strip). */
export function wavelengthRGB(wl) {
  let r = 0, g = 0, b = 0;
  if (wl >= 380 && wl < 440) { r = -(wl - 440) / 60; b = 1; }
  else if (wl < 490) { g = (wl - 440) / 50; b = 1; }
  else if (wl < 510) { g = 1; b = -(wl - 510) / 20; }
  else if (wl < 580) { r = (wl - 510) / 70; g = 1; }
  else if (wl < 645) { r = 1; g = -(wl - 645) / 65; }
  else if (wl <= 780) { r = 1; }
  let f = 1;
  if (wl < 420) f = 0.3 + 0.7 * (wl - 380) / 40;
  else if (wl > 700) f = 0.3 + 0.7 * (780 - wl) / 80;
  const c = (v) => Math.round(255 * Math.pow(Math.max(0, v * f), 0.8));
  return `rgb(${c(r)},${c(g)},${c(b)})`;
}

/** Map t in [0,1] to a violet→teal→amber ramp (ARTISTIC colouring of refractive index). */
export function ramp(t) {
  t = Math.max(0, Math.min(1, t));
  const stops = [[40, 30, 90], [110, 90, 255], [63, 214, 198], [255, 200, 90]];
  const s = t * (stops.length - 1), i = Math.min(stops.length - 2, Math.floor(s)), u = s - i;
  const c = stops[i].map((v, k) => Math.round(v + (stops[i + 1][k] - v) * u));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
