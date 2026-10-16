// Serialized into Chrome. These charts use flat, axis-aligned rectangles.
// Fail on unsupported paint rather than silently measuring the page color.
export function measureSvgContrast() {
  const rgba = (value) => {
    if (value === "none") return [0, 0, 0, 0];
    if (/^rgba?\(/.test(value)) {
      const n = value.match(/[\d.]+/g).map(Number);
      return [...n.slice(0, 3), n[3] ?? 1];
    }
    if (value.startsWith("color(srgb ")) {
      const [rgb, alpha = "1"] = value.slice(11, -1).split("/");
      return [...rgb.trim().split(/\s+/).map((n) => Number(n) * 255), Number(alpha)];
    }
    throw new Error(`Unsupported SVG color: ${value}`);
  };
  const over = (fg, bg) => fg.slice(0, 3).map((v, i) => v * fg[3] + bg[i] * (1 - fg[3]));
  const luminance = (rgb) => rgb.map((v) => {
    const c = v / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  }).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
  const ratio = (a, b) => (Math.max(luminance(a), luminance(b)) + 0.05)
    / (Math.min(luminance(a), luminance(b)) + 0.05);
  const plainStyle = (el) => {
    const style = getComputedStyle(el);
    if (style.opacity !== "1" || style.filter !== "none" || style.clipPath !== "none"
        || style.maskImage !== "none" || style.mixBlendMode !== "normal" || style.backgroundImage !== "none") {
      throw new Error("SVG contrast probe needs support for this opacity/filter/clip/mask/blend");
    }
    return style;
  };
  const backgroundOf = (el) => {
    const ancestors = [];
    for (let node = el; node; node = node.parentElement) ancestors.unshift(node);
    return ancestors.reduce((bg, node) => over(rgba(plainStyle(node).backgroundColor), bg), [255, 255, 255]);
  };
  const box = (el) => {
    const matrix = el.getScreenCTM();
    if (!matrix || Math.abs(matrix.b) > 1e-6 || Math.abs(matrix.c) > 1e-6) {
      throw new Error("SVG contrast probe needs support for rotated/skewed paint");
    }
    const r = el.getBoundingClientRect();
    return { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
  };
  const intersection = (a, b) => {
    const r = { left: Math.max(a.left, b.left), right: Math.min(a.right, b.right),
      top: Math.max(a.top, b.top), bottom: Math.min(a.bottom, b.bottom) };
    return r.right > r.left && r.bottom > r.top ? r : null;
  };
  const samples = Array.from(document.querySelectorAll("main svg text")).map((text) => {
    const svg = text.ownerSVGElement;
    if (text.parentElement !== svg || text.children.length || svg.querySelector("g")) {
      throw new Error("SVG contrast probe needs support for grouped paint");
    }
    const style = plainStyle(text);
    const bounds = box(text);
    if (!text.textContent.trim() || style.visibility !== "visible" || !text.getClientRects().length
        || bounds.right <= bounds.left || bounds.bottom <= bounds.top) {
      throw new Error("Expected chart text is empty or hidden");
    }
    if (style.stroke !== "none") throw new Error("SVG text strokes need a separate contrast check");
    let regions = [{ ...bounds, color: backgroundOf(text), source: "paper" }];
    // SVG paints siblings in document order. Partition the text bounds wherever
    // an earlier bar covers them, preserving paper and any overlapping bars.
    for (const shape of svg.querySelectorAll("rect,line,path,circle,ellipse,polygon,polyline,use,image,foreignObject")) {
      if (!(shape.compareDocumentPosition(text) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
      const paint = plainStyle(shape);
      if (paint.display === "none" || paint.visibility !== "visible") continue;
      const area = box(shape);
      if (paint.stroke !== "none") {
        const m = shape.getScreenCTM();
        const padding = parseFloat(paint.strokeWidth) * Math.max(Math.abs(m.a), Math.abs(m.d)) / 2;
        area.left -= padding; area.right += padding; area.top -= padding; area.bottom += padding;
      }
      if (!intersection(bounds, area)) continue;
      if (shape.tagName !== "rect" || paint.stroke !== "none"
          || parseFloat(paint.rx) || parseFloat(paint.ry)) {
        throw new Error(`Unsupported SVG paint beneath '${text.textContent}': ${shape.tagName}`);
      }
      const fill = rgba(paint.fill);
      fill[3] *= Number(paint.fillOpacity);
      if (fill[3] === 0) continue;
      regions = regions.flatMap((region) => {
        const overlap = intersection(region, area);
        if (!overlap) return [region];
        const outside = [
          { ...region, bottom: overlap.top }, { ...region, top: overlap.bottom },
          { ...region, top: overlap.top, bottom: overlap.bottom, right: overlap.left },
          { ...region, top: overlap.top, bottom: overlap.bottom, left: overlap.right },
        ].filter((r) => r.right > r.left && r.bottom > r.top);
        return [...outside, { ...overlap, color: over(fill, region.color), source: shape.getAttribute("class") || "rect" }];
      });
    }
    const fill = rgba(style.fill);
    fill[3] *= Number(style.fillOpacity);
    const backgrounds = regions.map((r) => ({ source: r.source, color: r.color,
      ratio: ratio(over(fill, r.color), r.color) }));
    return { chart: svg.parentElement.id, text: text.textContent.trim(),
      className: text.getAttribute("class") || "", fill: style.fill, backgrounds,
      ratio: Math.min(...backgrounds.map((bg) => bg.ratio)) };
  });
  return { charts: document.querySelectorAll("main svg:has(text)").length, samples };
}
