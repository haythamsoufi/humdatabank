/** Shared SVG line-chart renderer for dashboard and chart-asset templates. */

function defaultLineChartEffects() {
  return { area_fill: false, line_shadow: false, marker_ring: false };
}

function resolveLineChartEffects(overrides) {
  const base = typeof LINE_CHART_EFFECTS !== "undefined" ? LINE_CHART_EFFECTS : defaultLineChartEffects();
  return { ...defaultLineChartEffects(), ...base, ...(overrides || {}) };
}

function hasValue(v) {
  return v !== null && v !== undefined;
}

function nearestValue(values, index, direction) {
  const step = direction < 0 ? -1 : 1;
  for (let i = index + step; i >= 0 && i < values.length; i += step) {
    if (hasValue(values[i])) return values[i];
  }
  return null;
}

function valueLabelAbove(index, value, values, annualTarget, yMax) {
  const prev = nearestValue(values, index, -1);
  const next = nearestValue(values, index, 1);
  let above = true;
  if (prev !== null && next !== null && value <= prev && value <= next) above = false;
  if (annualTarget && Math.abs(value - annualTarget) < yMax * 0.08) {
    above = value > annualTarget;
  }
  return above;
}

function lineSegments(coords) {
  const segments = [];
  let current = [];
  for (const c of coords) {
    if (!c) {
      if (current.length > 1) segments.push(current);
      current = [];
      continue;
    }
    current.push(c);
  }
  if (current.length > 1) segments.push(current);
  return segments;
}

const LABEL_ABOVE_OFFSET = 10;
const LABEL_BELOW_OFFSET = 16;
const MIN_LABEL_CLEARANCE_FROM_BOTTOM = 12;

function valueLabelY(cy, above, bottomY) {
  if (above) return cy - LABEL_ABOVE_OFFSET;
  const belowY = cy + LABEL_BELOW_OFFSET;
  if (belowY > bottomY - MIN_LABEL_CLEARANCE_FROM_BOTTOM) {
    return cy - LABEL_ABOVE_OFFSET;
  }
  return belowY;
}

function targetLabelLayout(values, valueLabels, annualTarget, annualTargetLabel, width, padL, padR, chartH) {
  if (!annualTarget) return { tagBelow: false, valueAbove: false, valueBelow: false };

  const numeric = values.filter(hasValue);
  const n = values.length;
  const yMax = Math.max(...numeric, annualTarget) * 1.18 || 1;
  const padT = 22;
  const padB = 8;
  const yScale = v => padT + (chartH - padT - padB) * (1 - v / yMax);
  const w = width - padL - padR;
  const xStep = n > 1 ? w / (n - 1) : 0;
  const xAt = i => ((padL + i * xStep) / width) * 100;
  const ty = yScale(annualTarget);

  let tagBelow = false;
  for (let i = 0; i < n; i++) {
    if (!valueLabels[i] || !hasValue(values[i]) || xAt(i) > 30) continue;
    const val = values[i];
    const above = valueLabelAbove(i, val, values, annualTarget, yMax);
    const ly = above ? yScale(val) - 10 : yScale(val) + 16;
    if (!(ty < ly - 10 || ty - 12 > ly)) {
      tagBelow = true;
      break;
    }
  }

  let valueAbove = false;
  let valueBelow = false;
  for (let i = 0; i < n; i++) {
    if (!valueLabels[i] || !hasValue(values[i]) || xAt(i) < 65) continue;
    const val = values[i];
    const above = valueLabelAbove(i, val, values, annualTarget, yMax);
    const ly = above ? yScale(val) - 10 : yScale(val) + 16;
    if (Math.abs(val - annualTarget) < yMax * 0.08) {
      valueAbove = !above;
      valueBelow = above;
      break;
    }
    if (Math.abs(ly - ty) < 12) {
      valueAbove = true;
      break;
    }
  }

  if (
    annualTargetLabel &&
    n &&
    valueLabels[n - 1] &&
    hasValue(values[n - 1]) &&
    Math.abs(values[n - 1] - annualTarget) < yMax * 0.02 &&
    valueLabels[n - 1] === annualTargetLabel
  ) {
    valueAbove = true;
  }

  return { tagBelow, valueAbove, valueBelow };
}

function renderLineChart(item, width, targetLabel, chartId, effects, options) {
  const fx = resolveLineChartEffects(effects);
  const opts = options || {};
  const showValueLabels = opts.showValueLabels !== false;
  const showTargetLabels = opts.showTargetLabels !== false;

  const values = item.values;
  const h = 110;
  const padL = CHART_PAD_L;
  const padR = CHART_PAD_R;
  const padT = 22;
  const padB = 8;
  const w = width - padL - padR;
  const allY = values.filter(hasValue);
  if (item.annual_target) allY.push(item.annual_target);
  const yMax = Math.max(...allY) * 1.18 || 1;
  const n = values.length;
  const xStep = n > 1 ? w / (n - 1) : 0;
  const yScale = v => padT + (h - padT - padB) * (1 - v / yMax);
  const xAt = i => padL + i * xStep;
  const bottomY = padT + (h - padT - padB);
  const uid = String(chartId || "line0").replace(/[^a-zA-Z0-9_-]/g, "");

  const coords = values.map((v, i) => (hasValue(v) ? [xAt(i), yScale(v)] : null));
  const segments = lineSegments(coords);

  let svg = `<svg class="line-chart-svg" viewBox="0 0 ${width} ${h}" preserveAspectRatio="xMinYMid meet" xmlns="http://www.w3.org/2000/svg">`;

  const isModern = (typeof DATA !== "undefined" && DATA.style === "modern");
  const markerR = (typeof MARKER_RADIUS !== "undefined" ? MARKER_RADIUS : (isModern ? 2.25 : 3.5));

  if (fx.area_fill || fx.line_shadow) {
    svg += "<defs>";
    if (fx.area_fill) {
      const topOp = isModern ? "0.16" : "0.10";
      const midOp = isModern ? "0.05" : "0.04";
      svg += `<linearGradient id="${uid}-area" gradientUnits="userSpaceOnUse" x1="0" y1="${padT}" x2="0" y2="${bottomY}">
        <stop offset="0%" stop-color="${COLORS.value}" stop-opacity="${topOp}"/>
        <stop offset="50%" stop-color="${COLORS.value}" stop-opacity="${midOp}"/>
        <stop offset="100%" stop-color="${COLORS.value}" stop-opacity="0"/>
      </linearGradient>`;
    }
    if (fx.line_shadow) {
      const dy = isModern ? "1.5" : "1";
      const blur = isModern ? "1.6" : "1.2";
      const opacity = isModern ? "0.18" : "0.14";
      svg += `<filter id="${uid}-shadow" x="-4%" y="-4%" width="108%" height="112%">
        <feDropShadow dx="0" dy="${dy}" stdDeviation="${blur}" flood-color="${COLORS.value}" flood-opacity="${opacity}"/>
      </filter>`;
    }
    svg += "</defs>";
  }

  if (item.annual_target) {
    const ty = yScale(item.annual_target);
    const layout = targetLabelLayout(
      values,
      item.value_labels,
      item.annual_target,
      item.annual_target_label,
      width,
      padL,
      padR,
      h,
    );
    const targetStroke = isModern
      ? `stroke="${COLORS.target}" stroke-width="1.5" stroke-dasharray="4 3"`
      : `stroke="${COLORS.target}" stroke-width="2"`;
    svg += `<line x1="${padL}" y1="${ty}" x2="${padL + w}" y2="${ty}" ${targetStroke}/>`;
    if (showTargetLabels && targetLabel) {
      const tagY = layout.tagBelow ? ty + 4 : ty - 5;
      const tagBaseline = layout.tagBelow ? "hanging" : "auto";
      svg += `<text x="${padL + 4}" y="${tagY}" fill="${COLORS.target}" font-size="9" font-weight="700" dominant-baseline="${tagBaseline}">${esc(targetLabel)}</text>`;
    }
    if (showTargetLabels && item.annual_target_label) {
      let valueY = ty;
      let valueBaseline = "middle";
      if (layout.valueAbove) {
        valueY = ty - 5;
        valueBaseline = "auto";
      } else if (layout.valueBelow) {
        valueY = ty + 4;
        valueBaseline = "hanging";
      }
      svg += `<text x="${padL + w + 6}" y="${valueY}" fill="${COLORS.target}" font-size="10" font-weight="700" dominant-baseline="${valueBaseline}">${esc(item.annual_target_label)}</text>`;
    }
  }

  if (fx.area_fill) {
    segments.forEach(seg => {
      const areaD =
        `M ${seg[0][0]},${seg[0][1]} ` +
        seg.slice(1).map(c => `L ${c[0]},${c[1]}`).join(" ") +
        ` L ${seg[seg.length - 1][0]},${bottomY} L ${seg[0][0]},${bottomY} Z`;
      svg += `<path d="${areaD}" fill="url(#${uid}-area)"/>`;
    });
  }

  const shadowAttr = fx.line_shadow ? ` filter="url(#${uid}-shadow)"` : "";
  const strokeWidth = (typeof LINE_STROKE_WIDTH !== "undefined" ? LINE_STROKE_WIDTH : 2.5);
  segments.forEach(seg => {
    const points = seg.map(c => c.join(",")).join(" ");
    svg += `<polyline points="${points}" fill="none" stroke="${COLORS.value}" stroke-width="${strokeWidth}" stroke-linejoin="round" stroke-linecap="round"${shadowAttr}/>`;
  });

  values.forEach((v, i) => {
    if (!hasValue(v)) return;
    const cx = xAt(i);
    const cy = yScale(v);
    if (fx.marker_ring) {
      const ringR = markerR + 1.5;
      svg += `<circle cx="${cx}" cy="${cy}" r="${ringR}" fill="#ffffff" stroke="${COLORS.value}" stroke-width="1.5"/>`;
      svg += `<circle cx="${cx}" cy="${cy}" r="${Math.max(markerR - 1, 1.5)}" fill="${COLORS.value}"/>`;
    } else {
      svg += `<circle cx="${cx}" cy="${cy}" r="${markerR}" fill="${COLORS.value}"/>`;
    }

    if (!showValueLabels) return;
    const label = item.value_labels[i];
    if (!label) return;

    const prev = nearestValue(values, i, -1);
    const next = nearestValue(values, i, 1);
    let above = true;
    if (prev !== null && next !== null && v <= prev && v <= next) above = false;
    if (item.annual_target && Math.abs(v - item.annual_target) < yMax * 0.08) {
      above = v > item.annual_target;
    }
    const ly = valueLabelY(cy, above, bottomY);
    svg += `<text x="${cx}" y="${ly}" text-anchor="middle" fill="${COLORS.value}" font-size="10" font-weight="700">${esc(label)}</text>`;
  });

  svg += "</svg>";
  return svg;
}
