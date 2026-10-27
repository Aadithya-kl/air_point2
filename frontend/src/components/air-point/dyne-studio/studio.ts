export type Category =
  "Colour" | "Text" | "Material" | "Shape" | "Notifications" | "Behaviour & Timing";
export type Adjustment =
  "Glass" | "Matte" | "Translucent" | "Font Size" | "Font Boldness" | "Roundness";
export type View =
  | { kind: "rest" }
  | { kind: "main" }
  | { kind: "category"; category: Category }
  | { kind: "materialGroup"; group: "Surface" | "Lighting" }
  | { kind: "fonts" }
  | { kind: "customColour" }
  | { kind: "extendedColours" }
  | {
      kind: "adjust";
      adjustment: Adjustment;
      parent: Category;
      parentGroup?: "Surface" | "Lighting";
    };
export type Settings = {
  accent: string;
  texture: string;
  font: string;
  fontSize: number;
  weight: number;
  intensity: number;
  matteIntensity: number;
  translucentIntensity: number;
  roundness: number;
  style: string;
  customRgb: { r: number; g: number; b: number };
};
export const initialSettings: Settings = {
  accent: "Gold",
  texture: "Glass",
  font: "System",
  fontSize: 23,
  weight: 400,
  intensity: 50,
  matteIntensity: 50,
  translucentIntensity: 50,
  roundness: 56,
  style: "Balanced",
  customRgb: { r: 140, g: 80, b: 255 },
};
export const colours = [
  ["Brown", "#a7784c"],
  ["Red", "#ef505c"],
  ["Blue", "#348cff"],
  ["Neon", "#b1ed4e"],
  ["Green", "#3cd6a0"],
  ["White", "#edf5ff"],
  ["Grey", "#8794a1"],
  ["Gold", "#f4c75b"],
  ["Purple", "#b37bea"],
  ["Orange", "#f7a34e"],
] as const;
export const innerRingColours = [
  ["Brown", "#a7784c"],
  ["Red", "#ef505c"],
  ["Blue", "#348cff"],
  ["Neon", "#b1ed4e"],
  ["Purple", "#b37bea"],
  ["Gold", "#f4c75b"],
  ["Green", "#3cd6a0"],
  ["Orange", "#FFA34D"],
] as const;

export const outerRingColours = [
  ["Cyan", "#48D8E8"],
  ["Teal", "#159E98"],
  ["Mint", "#91E7C0"],
  ["Lime", "#C4EE52"],
  ["Yellow", "#F4DB55"],
  ["Amber", "#ED9D42"],
  ["Coral", "#FF8075"],
  ["Crimson", "#BD334E"],
  ["Rose", "#F18BB3"],
  ["Magenta", "#DC5BD8"],
] as const;

export const extendedColours = [...innerRingColours, ...outerRingColours] as const;
export const fonts: Record<string, string> = {
  System: "Arial, Helvetica, sans-serif",
  Mono: '"Courier New", monospace',
  Humanist: "Verdana, sans-serif",
};
export function rgbHex({ r, g, b }: Settings["customRgb"]) {
  return `#${[r, g, b]
    .map((v) => Math.round(v).toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase()}`;
}
export function accentValue(settings: Settings) {
  return settings.accent === "Custom"
    ? rgbHex(settings.customRgb)
    : ([...colours, ...extendedColours].find((c) => c[0] === settings.accent)?.[1] ?? "#f4c75b");
}
export const adjustmentConfig: Record<
  Adjustment,
  { key: keyof Settings; min: number; max: number; midpoint: number; step: number; unit: string }
> = {
  Glass: { key: "intensity", min: 0, max: 100, midpoint: 50, step: 1, unit: "%" },
  Matte: { key: "matteIntensity", min: 0, max: 100, midpoint: 50, step: 1, unit: "%" },
  Translucent: { key: "translucentIntensity", min: 0, max: 100, midpoint: 50, step: 1, unit: "%" },
  "Font Size": { key: "fontSize", min: 18, max: 28, midpoint: 23, step: 1, unit: "px" },
  "Font Boldness": { key: "weight", min: 300, max: 800, midpoint: 550, step: 100, unit: "" },
  Roundness: { key: "roundness", min: 28, max: 56, midpoint: 42, step: 1, unit: "px" },
};

// A shared perimeter parameter keeps the inner and outer shell seams aligned.
export function stadiumPoint(t: number, radius: number) {
  const r = 150,
    straight = 320,
    length = 2 * straight + 2 * Math.PI * r;
  let d = Math.max(0, Math.min(1, t)) * length;
  if (d <= straight / 2) return { x: 430 + d, y: 240 - radius };
  d -= straight / 2;
  if (d <= Math.PI * r) {
    const a = -Math.PI / 2 + d / r;
    return { x: 590 + radius * Math.cos(a), y: 240 + radius * Math.sin(a) };
  }
  d -= Math.PI * r;
  if (d <= straight) return { x: 590 - d, y: 240 + radius };
  d -= straight;
  if (d <= Math.PI * r) {
    const a = Math.PI / 2 + d / r;
    return { x: 270 + radius * Math.cos(a), y: 240 + radius * Math.sin(a) };
  }
  d -= Math.PI * r;
  return { x: 270 + d, y: 240 - radius };
}

export function perimeterPath(start: number, end: number, radius: number, move = true) {
  const length = 640 + 300 * Math.PI;
  const boundaries = [160, 160 + 150 * Math.PI, 480 + 150 * Math.PI, 480 + 300 * Math.PI].map(
    (d) => d / length,
  );
  const cuts = boundaries.filter((t) => t > Math.min(start, end) && t < Math.max(start, end));
  if (end < start) cuts.reverse();
  const points = [start, ...cuts, end];
  const first = stadiumPoint(start, radius);
  let path = `${move ? "M" : "L"} ${first.x} ${first.y}`;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1]!;
    const curr = points[i]!;
    const middle = (prev + curr) / 2;
    const b0 = boundaries[0] ?? 0;
    const b1 = boundaries[1] ?? 0;
    const b2 = boundaries[2] ?? 0;
    const b3 = boundaries[3] ?? 0;
    const curved = (middle > b0 && middle < b1) || (middle > b2 && middle < b3);
    const p = stadiumPoint(curr, radius);
    path += curved
      ? ` A ${radius} ${radius} 0 0 ${end > start ? 1 : 0} ${p.x} ${p.y}`
      : ` L ${p.x} ${p.y}`;
  }
  return path;
}

// Fine-adjustment controls use an open stadium path: minimum at the upper-left,
// maximum at the upper-right, and the midpoint at the bottom centre. Keeping
// this separate from the closed shell geometry preserves segment alignment.
export type StadiumTrackFrame = { x: number; y: number; nx: number; ny: number };
export const TRACK_LEFT = 270;
export const TRACK_RIGHT = 590;
export const TRACK_CENTRE_Y = 240;
export const TRACK_STRAIGHT = TRACK_RIGHT - TRACK_LEFT;

export function stadiumTrackFrame(t: number, radius: number): StadiumTrackFrame {
  const progress = Math.max(0, Math.min(1, t));
  const safeRadius = Math.max(1, radius);
  const arc = Math.PI * safeRadius;
  const total = TRACK_STRAIGHT + 2 * arc;
  let distance = progress * total;
  if (distance <= arc) {
    const angle = -Math.PI / 2 - distance / safeRadius;
    return {
      x: TRACK_LEFT + safeRadius * Math.cos(angle),
      y: TRACK_CENTRE_Y + safeRadius * Math.sin(angle),
      nx: Math.cos(angle),
      ny: Math.sin(angle),
    };
  }
  distance -= arc;
  if (distance <= TRACK_STRAIGHT) {
    return { x: TRACK_LEFT + distance, y: TRACK_CENTRE_Y + safeRadius, nx: 0, ny: 1 };
  }
  distance -= TRACK_STRAIGHT;
  const angle = Math.PI / 2 - distance / safeRadius;
  return {
    x: TRACK_RIGHT + safeRadius * Math.cos(angle),
    y: TRACK_CENTRE_Y + safeRadius * Math.sin(angle),
    nx: Math.cos(angle),
    ny: Math.sin(angle),
  };
}

export function stadiumTrackPoint(t: number, radius: number) {
  const { x, y } = stadiumTrackFrame(t, radius);
  return { x, y };
}

export function stadiumTrackPath(start: number, end: number, radius: number) {
  const safeRadius = Math.max(1, radius);
  const total = TRACK_STRAIGHT + 2 * Math.PI * safeRadius;
  const boundaries = [
    (Math.PI * safeRadius) / 2,
    Math.PI * safeRadius,
    Math.PI * safeRadius + TRACK_STRAIGHT,
    Math.PI * safeRadius + TRACK_STRAIGHT + (Math.PI * safeRadius) / 2,
  ].map((d) => d / total);
  const cuts = boundaries.filter((t) => t > Math.min(start, end) && t < Math.max(start, end));
  if (end < start) cuts.reverse();
  const stops = [start, ...cuts, end];
  const first = stadiumTrackPoint(start, safeRadius);
  let path = `M ${first.x} ${first.y}`;
  for (let i = 1; i < stops.length; i++) {
    const a = stops[i - 1] ?? 0,
      b = stops[i] ?? 1,
      middle = (a + b) / 2;
    const distanceAtMiddle = middle * total;
    const isArc =
      distanceAtMiddle < Math.PI * safeRadius ||
      distanceAtMiddle > Math.PI * safeRadius + TRACK_STRAIGHT;
    const point = stadiumTrackPoint(b, safeRadius);
    if (isArc)
      path += ` A ${safeRadius} ${safeRadius} 0 0 ${end > start ? 0 : 1} ${point.x} ${point.y}`;
    else path += ` L ${point.x} ${point.y}`;
  }
  return path;
}

// Continuous, jump-free projection onto the open stadium track
export function stadiumTrackProject(px: number, py: number, radius: number): number {
  const safeRadius = Math.max(1, radius);
  const arc = Math.PI * safeRadius;
  const total = TRACK_STRAIGHT + 2 * arc;

  // If in the top opening region above the capsule
  if (py < TRACK_CENTRE_Y && px >= TRACK_LEFT && px <= TRACK_RIGHT) {
    return px < (TRACK_LEFT + TRACK_RIGHT) / 2 ? 0 : 1;
  }

  if (px <= TRACK_LEFT) {
    const angle = Math.atan2(py - TRACK_CENTRE_Y, px - TRACK_LEFT);
    let delta = -Math.PI / 2 - angle;
    while (delta < 0) delta += 2 * Math.PI;
    while (delta >= 2 * Math.PI) delta -= 2 * Math.PI;
    if (delta > Math.PI) delta = py > TRACK_CENTRE_Y ? Math.PI : 0;
    return Math.max(0, Math.min(1, (delta * safeRadius) / total));
  }

  if (px >= TRACK_RIGHT) {
    const angle = Math.atan2(py - TRACK_CENTRE_Y, px - TRACK_RIGHT);
    let delta = Math.PI / 2 - angle;
    while (delta < 0) delta += 2 * Math.PI;
    while (delta >= 2 * Math.PI) delta -= 2 * Math.PI;
    if (delta > Math.PI) delta = py > TRACK_CENTRE_Y ? 0 : Math.PI;
    return Math.max(0, Math.min(1, (arc + TRACK_STRAIGHT + delta * safeRadius) / total));
  }

  // Bottom straight region
  return Math.max(0, Math.min(1, (arc + (px - TRACK_LEFT)) / total));
}

// Complete concentric stadium loops for Custom RGB rings with visual end gap
export const RGB_GAP = 16;

export function stadiumLoopPerimeterFrame(distance: number, radius: number): StadiumTrackFrame {
  const safeRadius = Math.max(1, radius);
  const arc = Math.PI * safeRadius;
  const total = 2 * TRACK_STRAIGHT + 2 * arc;
  let d = Math.max(0, Math.min(total, distance));

  // 1. Bottom straight: left to right (270 to 590 at y = 240 + radius)
  if (d <= TRACK_STRAIGHT) {
    return { x: TRACK_LEFT + d, y: TRACK_CENTRE_Y + safeRadius, nx: 0, ny: 1 };
  }
  d -= TRACK_STRAIGHT;

  // 2. Right semicircle: bottom to top (counter-clockwise)
  if (d <= arc) {
    const angle = Math.PI / 2 - d / safeRadius;
    return {
      x: TRACK_RIGHT + safeRadius * Math.cos(angle),
      y: TRACK_CENTRE_Y + safeRadius * Math.sin(angle),
      nx: Math.cos(angle),
      ny: Math.sin(angle),
    };
  }
  d -= arc;

  // 3. Top straight: right to left (590 to 270 at y = 240 - radius)
  if (d <= TRACK_STRAIGHT) {
    return { x: TRACK_RIGHT - d, y: TRACK_CENTRE_Y - safeRadius, nx: 0, ny: -1 };
  }
  d -= TRACK_STRAIGHT;

  // 4. Left semicircle: top to bottom (counter-clockwise)
  const angle = -Math.PI / 2 - d / safeRadius;
  return {
    x: TRACK_LEFT + safeRadius * Math.cos(angle),
    y: TRACK_CENTRE_Y + safeRadius * Math.sin(angle),
    nx: Math.cos(angle),
    ny: Math.sin(angle),
  };
}

export function stadiumLoopFrame(t: number, radius: number): StadiumTrackFrame {
  const safeRadius = Math.max(1, radius);
  const arc = Math.PI * safeRadius;
  const total = 2 * TRACK_STRAIGHT + 2 * arc;
  const dStart = RGB_GAP / 2;
  const dEnd = total - RGB_GAP / 2;
  const dActive = dEnd - dStart;
  const progress = Math.max(0, Math.min(1, t));
  const d = dStart + progress * dActive;
  return stadiumLoopPerimeterFrame(d, safeRadius);
}

export function stadiumLoopPoint(t: number, radius: number) {
  const { x, y } = stadiumLoopFrame(t, radius);
  return { x, y };
}

export function stadiumLoopBasePath(radius: number): string {
  const safeRadius = Math.max(1, radius);
  const arc = Math.PI * safeRadius;
  const total = 2 * TRACK_STRAIGHT + 2 * arc;
  const dStart = RGB_GAP / 2;
  const dEnd = total - RGB_GAP / 2;

  const pStart = stadiumLoopPerimeterFrame(dStart, safeRadius);
  const pB1 = { x: TRACK_RIGHT, y: TRACK_CENTRE_Y + safeRadius };
  const pB2 = { x: TRACK_RIGHT, y: TRACK_CENTRE_Y - safeRadius };
  const pB3 = { x: TRACK_LEFT, y: TRACK_CENTRE_Y - safeRadius };
  const pEnd = stadiumLoopPerimeterFrame(dEnd, safeRadius);

  return (
    `M ${pStart.x} ${pStart.y} ` +
    `L ${pB1.x} ${pB1.y} ` +
    `A ${safeRadius} ${safeRadius} 0 0 0 ${pB2.x} ${pB2.y} ` +
    `L ${pB3.x} ${pB3.y} ` +
    `A ${safeRadius} ${safeRadius} 0 0 0 ${pEnd.x} ${pEnd.y}`
  );
}

export function stadiumLoopActivePath(t: number, radius: number): string {
  const progress = Math.max(0, Math.min(1, t));
  if (progress <= 0.0005) return "";

  const safeRadius = Math.max(1, radius);
  const arc = Math.PI * safeRadius;
  const total = 2 * TRACK_STRAIGHT + 2 * arc;
  const dStart = RGB_GAP / 2;
  const dEnd = total - RGB_GAP / 2;
  const targetD = dStart + progress * (dEnd - dStart);

  const pStart = stadiumLoopPerimeterFrame(dStart, safeRadius);
  let path = `M ${pStart.x} ${pStart.y}`;

  if (targetD <= TRACK_STRAIGHT) {
    const pCurrent = stadiumLoopPerimeterFrame(targetD, safeRadius);
    return `${path} L ${pCurrent.x} ${pCurrent.y}`;
  }
  path += ` L ${TRACK_RIGHT} ${TRACK_CENTRE_Y + safeRadius}`;

  const bRightEnd = TRACK_STRAIGHT + arc;
  if (targetD <= bRightEnd) {
    const pCurrent = stadiumLoopPerimeterFrame(targetD, safeRadius);
    return `${path} A ${safeRadius} ${safeRadius} 0 0 0 ${pCurrent.x} ${pCurrent.y}`;
  }
  path += ` A ${safeRadius} ${safeRadius} 0 0 0 ${TRACK_RIGHT} ${TRACK_CENTRE_Y - safeRadius}`;

  const bTopEnd = 2 * TRACK_STRAIGHT + arc;
  if (targetD <= bTopEnd) {
    const pCurrent = stadiumLoopPerimeterFrame(targetD, safeRadius);
    return `${path} L ${pCurrent.x} ${pCurrent.y}`;
  }
  path += ` L ${TRACK_LEFT} ${TRACK_CENTRE_Y - safeRadius}`;

  const pCurrent = stadiumLoopPerimeterFrame(targetD, safeRadius);
  return `${path} A ${safeRadius} ${safeRadius} 0 0 0 ${pCurrent.x} ${pCurrent.y}`;
}

export function stadiumLoopProject(px: number, py: number, radius: number): number {
  const safeRadius = Math.max(1, radius);
  const arc = Math.PI * safeRadius;
  const total = 2 * TRACK_STRAIGHT + 2 * arc;
  const dStart = RGB_GAP / 2;
  const dEnd = total - RGB_GAP / 2;
  const dActive = dEnd - dStart;

  // 1. Bottom straight
  const x1 = Math.max(TRACK_LEFT, Math.min(TRACK_RIGHT, px));
  const y1 = TRACK_CENTRE_Y + safeRadius;
  const d1 = x1 - TRACK_LEFT;
  const distSq1 = (px - x1) * (px - x1) + (py - y1) * (py - y1);

  // 2. Right semicircle (centered at TRACK_RIGHT, TRACK_CENTRE_Y)
  const angle2 = Math.atan2(py - TRACK_CENTRE_Y, px - TRACK_RIGHT);
  let delta2 = Math.PI / 2 - angle2;
  while (delta2 < 0) delta2 += 2 * Math.PI;
  while (delta2 >= 2 * Math.PI) delta2 -= 2 * Math.PI;
  if (delta2 > Math.PI) delta2 = py > TRACK_CENTRE_Y ? 0 : Math.PI;
  const x2 = TRACK_RIGHT + safeRadius * Math.cos(Math.PI / 2 - delta2);
  const y2 = TRACK_CENTRE_Y + safeRadius * Math.sin(Math.PI / 2 - delta2);
  const d2 = TRACK_STRAIGHT + delta2 * safeRadius;
  const distSq2 = (px - x2) * (px - x2) + (py - y2) * (py - y2);

  // 3. Top straight
  const x3 = Math.max(TRACK_LEFT, Math.min(TRACK_RIGHT, px));
  const y3 = TRACK_CENTRE_Y - safeRadius;
  const d3 = TRACK_STRAIGHT + arc + (TRACK_RIGHT - x3);
  const distSq3 = (px - x3) * (px - x3) + (py - y3) * (py - y3);

  // 4. Left semicircle (centered at TRACK_LEFT, TRACK_CENTRE_Y)
  const angle4 = Math.atan2(py - TRACK_CENTRE_Y, px - TRACK_LEFT);
  let delta4 = -Math.PI / 2 - angle4;
  while (delta4 < 0) delta4 += 2 * Math.PI;
  while (delta4 >= 2 * Math.PI) delta4 -= 2 * Math.PI;
  if (delta4 > Math.PI) delta4 = py > TRACK_CENTRE_Y ? Math.PI : 0;
  const x4 = TRACK_LEFT + safeRadius * Math.cos(-Math.PI / 2 - delta4);
  const y4 = TRACK_CENTRE_Y + safeRadius * Math.sin(-Math.PI / 2 - delta4);
  const d4 = 2 * TRACK_STRAIGHT + arc + delta4 * safeRadius;
  const distSq4 = (px - x4) * (px - x4) + (py - y4) * (py - y4);

  let bestD = d1;
  let minDistSq = distSq1;
  if (distSq2 < minDistSq) {
    minDistSq = distSq2;
    bestD = d2;
  }
  if (distSq3 < minDistSq) {
    minDistSq = distSq3;
    bestD = d3;
  }
  if (distSq4 < minDistSq) {
    minDistSq = distSq4;
    bestD = d4;
  }

  return Math.max(0, Math.min(1, (bestD - dStart) / dActive));
}

// Stadium shell segments (clockwise starting from top-left)
export function shellPoint(t: number, radius: number) {
  const r = 150,
    straight = 320,
    length = 2 * straight + 2 * Math.PI * r;
  let d = Math.max(0, Math.min(1, t)) * length;
  if (d <= straight) return { x: 270 + d, y: 240 - radius };
  d -= straight;
  if (d <= Math.PI * r) {
    const a = -Math.PI / 2 + d / r;
    return { x: 590 + radius * Math.cos(a), y: 240 + radius * Math.sin(a) };
  }
  d -= Math.PI * r;
  if (d <= straight) return { x: 590 - d, y: 240 + radius };
  d -= straight;
  const a = Math.PI / 2 + d / r;
  return { x: 270 + radius * Math.cos(a), y: 240 + radius * Math.sin(a) };
}

export function shellArc(t1: number, t2: number, radius: number, move = true) {
  const r = 150,
    straight = 320,
    length = 2 * straight + 2 * Math.PI * r;
  const boundaries = [straight, straight + Math.PI * r, 2 * straight + Math.PI * r].map(
    (d) => d / length,
  );
  const forward = t2 >= t1;
  const minT = Math.min(t1, t2),
    maxT = Math.max(t1, t2);
  const cuts = boundaries.filter((b) => b > minT && b < maxT);
  if (!forward) cuts.reverse();
  const stops = [t1, ...cuts, t2];
  const p0 = shellPoint(t1, radius);
  let d = `${move ? "M" : "L"} ${p0.x} ${p0.y}`;
  for (let i = 1; i < stops.length; i++) {
    const a = stops[i - 1] ?? 0,
      b = stops[i] ?? 1;
    const mid = (a + b) / 2;
    const midD = mid * length;
    const isCurve =
      (midD > straight && midD < straight + Math.PI * r) || midD > 2 * straight + Math.PI * r;
    const pb = shellPoint(b, radius);
    if (isCurve) {
      d += ` A ${radius} ${radius} 0 0 ${forward ? 1 : 0} ${pb.x} ${pb.y}`;
    } else {
      d += ` L ${pb.x} ${pb.y}`;
    }
  }
  return d;
}

export function shellArcClockwise(t1: number, t2: number, radius: number, move = true): string {
  if (t1 <= t2) {
    return shellArc(t1, t2, radius, move);
  }
  const arc1 = shellArc(t1, 1.0, radius, move);
  const arc2 = shellArc(0.0, t2, radius, false);
  return `${arc1} ${arc2}`;
}

export function shellArcCounterClockwise(
  t1: number,
  t2: number,
  radius: number,
  move = false,
): string {
  if (t1 >= t2) {
    return shellArc(t1, t2, radius, move);
  }
  const arc1 = shellArc(t1, 0.0, radius, move);
  const arc2 = shellArc(1.0, t2, radius, false);
  return `${arc1} ${arc2}`;
}

export function shellSegmentPath(t1: number, t2: number, outerR = 165, innerR = 78) {
  const outer = shellArcClockwise(t1, t2, outerR, true);
  const inner = shellArcCounterClockwise(t2, t1, innerR, false);
  return `${outer} ${inner} Z`;
}
