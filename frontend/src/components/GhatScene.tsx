import { memo } from "react";
import { useLocation } from "react-router-dom";

/**
 * The Banaras theme's art: the ghats at dawn along the foot of the desk. Havelis with jharokhas,
 * temple shikharas, chhatris and the big ghat umbrellas over the steps; the Ganga below with
 * boats and floating diyas; the sun coming up behind. It draws itself from left to right like the
 * light coming over the river, then the water moves, the boats rock and the diyas flicker.
 */

type Line = { d: string; delay: number; gold?: boolean; bold?: boolean };

const BASE = 258; // where the buildings stand, at the top of the steps
const W = 1600;
const delayAt = (x: number) => 0.15 + (x / W) * 2.2;

function haveli(x: number, w: number, h: number, out: Line[]) {
  const top = BASE - h;
  const at = delayAt(x);
  out.push({ d: `M${x} ${BASE} V${top} H${x + w} V${BASE}`, delay: at, bold: true });
  // Kangura: the stepped parapet along the roof.
  let p = `M${x - 4} ${top}`;
  for (let i = x - 4; i < x + w + 4; i += 12) p += ` h6 v-5 h6 v5`;
  out.push({ d: p, delay: at + 0.2 });
  const floors = Math.max(2, Math.round(h / 42));
  const bay = 26;
  const bays = Math.floor((w - 16) / bay);
  for (let f = 0; f < floors; f++) {
    const y = top + 18 + f * ((h - 30) / floors);
    out.push({ d: `M${x} ${y - 6} H${x + w}`, delay: at + 0.25 + f * 0.05 });
    for (let b = 0; b < bays; b++) {
      const wx = x + 10 + b * bay;
      // An arched window; every few bays a jharokha balcony juts out.
      out.push({ d: `M${wx + 4} ${y + 18} V${y + 6} Q${wx + 11} ${y - 2} ${wx + 18} ${y + 6} V${y + 18}`, delay: at + 0.3 + b * 0.02 });
      if ((b + f) % 3 === 1) out.push({ d: `M${wx} ${y + 20} h22 l-3 6 h-16 z M${wx + 2} ${y + 6} q9 -12 18 0`, delay: at + 0.4 + b * 0.02, gold: true });
    }
  }
  out.push({ d: `M${x + w / 2 - 9} ${BASE} V${BASE - 22} Q${x + w / 2} ${BASE - 32} ${x + w / 2 + 9} ${BASE - 22} V${BASE}`, delay: at + 0.3 });
}

function shikhara(x: number, w: number, h: number, out: Line[]) {
  const at = delayAt(x);
  const bodyTop = BASE - 46;
  const cx = x + w / 2;
  out.push({ d: `M${x} ${BASE} V${BASE - 14} H${x + w} V${BASE}`, delay: at });
  out.push({ d: `M${x + 6} ${BASE - 14} V${bodyTop} H${x + w - 6} V${BASE - 14}`, delay: at + 0.1, bold: true });
  out.push({ d: `M${cx - 8} ${BASE - 14} V${BASE - 34} Q${cx} ${BASE - 44} ${cx + 8} ${BASE - 34} V${BASE - 14}`, delay: at + 0.15 });
  // The curved spire, with its bands, the amalaka and the kalash on top.
  const apex = bodyTop - h;
  out.push({ d: `M${x + 8} ${bodyTop} C${x + 10} ${bodyTop - h * 0.55} ${cx - 10} ${apex + 12} ${cx} ${apex} C${cx + 10} ${apex + 12} ${x + w - 10} ${bodyTop - h * 0.55} ${x + w - 8} ${bodyTop}`, delay: at + 0.2, bold: true });
  for (let i = 1; i <= 3; i++) {
    const y = bodyTop - (h * i) / 4;
    const half = (w / 2 - 8) * (1 - (i / 4) * 0.62);
    out.push({ d: `M${cx - half} ${y} Q${cx} ${y - 5} ${cx + half} ${y}`, delay: at + 0.3 + i * 0.05 });
  }
  out.push({ d: `M${cx - 9} ${apex - 2} a9 4 0 1 0 18 0 a9 4 0 1 0 -18 0`, delay: at + 0.5, gold: true });
  out.push({ d: `M${cx} ${apex - 6} q-5 -6 0 -12 q5 6 0 12 M${cx} ${apex - 18} V${apex - 38} l16 6 l-16 6`, delay: at + 0.6, gold: true });
}

function domes(x: number, w: number, out: Line[]) {
  const at = delayAt(x);
  const top = BASE - 70;
  out.push({ d: `M${x} ${BASE} V${top} H${x + w} V${BASE}`, delay: at, bold: true });
  for (let i = 0; i < 3; i++) out.push({ d: `M${x + 12 + i * (w - 24) / 2.2} ${BASE} V${top + 22} q${(w - 24) / 8.8} -14 ${(w - 24) / 4.4} 0 V${BASE}`, delay: at + 0.15 + i * 0.05 });
  const cx = x + w / 2;
  out.push({ d: `M${x + 14} ${top} Q${x + 10} ${top - 40} ${cx} ${top - 58} Q${x + w - 10} ${top - 40} ${x + w - 14} ${top}`, delay: at + 0.3, bold: true });
  out.push({ d: `M${cx} ${top - 58} v-10 M${cx - 4} ${top - 64} h8`, delay: at + 0.5, gold: true });
  for (const sx of [x + 6, x + w - 22]) out.push({ d: `M${sx} ${top} v-10 h16 v10 M${sx - 2} ${top - 10} q10 -14 20 0`, delay: at + 0.4 });
}

function chhatri(x: number, out: Line[]) {
  const at = delayAt(x);
  const y = BASE - 8;
  out.push({ d: `M${x - 18} ${BASE} h36 M${x - 14} ${y} V${y - 30} M${x + 14} ${y} V${y - 30} M${x - 2} ${y} V${y - 30}`, delay: at });
  out.push({ d: `M${x - 22} ${y - 30} h44 M${x - 18} ${y - 30} Q${x} ${y - 62} ${x + 18} ${y - 30} M${x} ${y - 52} v-8`, delay: at + 0.15, gold: true });
}

function umbrella(x: number, y: number, out: Line[]) {
  const at = delayAt(x) + 0.4;
  out.push({ d: `M${x} ${y + 26} V${y}`, delay: at });
  out.push({ d: `M${x - 30} ${y + 4} Q${x} ${y - 16} ${x + 30} ${y + 4} Z M${x - 30} ${y + 4} l4 4 M${x - 15} ${y - 2} l2 5 M${x + 15} ${y - 2} l-2 5 M${x + 30} ${y + 4} l-4 4`, delay: at + 0.1, gold: true });
  out.push({ d: `M${x - 18} ${y + 26} h36 v-6 h-36 z`, delay: at + 0.2 });
}

function boat(x: number, y: number, w: number): Line[] {
  const at = delayAt(x) + 0.8;
  return [
    { d: `M${x} ${y} Q${x + w / 2} ${y + 18} ${x + w} ${y} L${x + w - 8} ${y + 2} H${x + 8} Z`, delay: at, bold: true },
    { d: `M${x + w * 0.3} ${y + 2} V${y - 14} Q${x + w * 0.5} ${y - 26} ${x + w * 0.7} ${y - 14} V${y + 2}`, delay: at + 0.15, gold: true },
    { d: `M${x + w * 0.86} ${y - 2} l18 26 M${x + w * 0.12} ${y - 18} v-2 a4 4 0 1 1 0 -1 M${x + w * 0.12} ${y - 12} v12`, delay: at + 0.25 },
  ];
}

function waves(y: number, amp: number, step: number): string {
  let d = `M-40 ${y}`;
  for (let x = -40; x < W + 40; x += step * 2) d += ` q${step / 2} ${-amp} ${step} 0 t${step} 0`;
  return d;
}

// Diyas set afloat at the evening aarti, still drifting at dawn, with marigolds among them.
const DIYAS: [number, number][] = [[150, 386], [196, 393], [244, 382], [292, 391], [612, 389], [664, 382], [718, 391], [1120, 391], [1172, 384], [1222, 392], [1276, 385], [1556, 388]];
const MARIGOLDS: [number, number][] = [[222, 397], [268, 389], [640, 394], [1146, 396], [1248, 397], [1530, 394]];

function buildScene() {
  const lines: Line[] = [];
  haveli(-6, 140, 122, lines);
  shikhara(146, 78, 108, lines);
  haveli(236, 176, 150, lines);
  chhatri(444, lines);
  domes(478, 112, lines);
  shikhara(606, 84, 140, lines);
  haveli(704, 196, 112, lines);
  shikhara(912, 70, 98, lines);
  haveli(994, 154, 136, lines);
  chhatri(1172, lines);
  domes(1206, 104, lines);
  haveli(1324, 290, 100, lines);
  // The ghat steps, wide and worn, down to the water.
  for (let i = 0; i < 8; i++) {
    const y = BASE + 6 + i * 8;
    let d = "";
    for (let x = -10; x < W + 10; x += 220) d += `M${x + (i % 2) * 16} ${y} h${196 - (i % 3) * 12} `;
    lines.push({ d, delay: 0.3 + i * 0.12 });
  }
  for (const x of [120, 340, 566, 772, 1052, 1288, 1490]) umbrella(x, 278, lines);
  lines.push({ d: `M0 322 H${W}`, delay: 1.1, bold: true });
  // The sun's road on the water.
  for (let i = 0; i < 5; i++) lines.push({ d: `M${1362 - i * 6} ${334 + i * 11} h${44 + i * 12}`, delay: 2.3 + i * 0.08, gold: true });
  return lines;
}

const SCENE = buildScene();
const BOATS: [number, number, number][] = [[300, 350, 112], [960, 370, 92], [1440, 344, 72]];

const Scene = memo(function Scene() {
  return (
    <>
      <defs>
        <linearGradient id="ganga" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="rgb(214 160 70)" stopOpacity="0.35" />
          <stop offset="1" stopColor="rgb(128 24 48)" stopOpacity="0.05" />
        </linearGradient>
      </defs>
      <g className="scene">
        <circle className="sun" cx="1384" cy="96" r="50" />
        <g className="gold">
          {Array.from({ length: 12 }, (_, i) => {
            const a = (Math.PI * (i + 0.5)) / 12;
            return <path key={i} className="stroke" pathLength={1} style={{ animationDelay: `${1.8 + i * 0.04}s` }}
              d={`M${1384 - Math.cos(a) * 62} ${96 - Math.sin(a) * 62} L${1384 - Math.cos(a) * 84} ${96 - Math.sin(a) * 84}`} />;
          })}
        </g>
        {[[180, 60], [240, 44], [720, 70]].map(([x, y], i) => (
          <path key={`b${i}`} className="bird stroke" pathLength={1} style={{ animationDelay: `${2 + i * 0.2}s, ${i * -12}s`, animationName: "draw, fly", animationDuration: "2s, 40s", animationIterationCount: "1, infinite", animationTimingFunction: "ease, linear" }}
            d={`M${x} ${y} q6 -6 12 0 q6 -6 12 0`} />
        ))}
        <rect className="river" x="0" y="322" width={W} height="80" />
        {SCENE.map((l, i) => (
          <path key={i} d={l.d} pathLength={1} className={l.gold ? "stroke gold" : "stroke"} style={{ animationDelay: `${l.delay}s`, strokeWidth: l.bold ? 1.8 : undefined }} />
        ))}
        {[[338, 4, 26], [356, 3, 34], [374, 3.5, 22], [392, 2.5, 40]].map(([y, amp, step], i) => (
          <g key={`w${i}`} className="wave"><path className="stroke" pathLength={1} style={{ animationDelay: `${1.2 + i * 0.15}s`, opacity: 0.7 - i * 0.1 }} d={waves(y, amp, step)} /></g>
        ))}
        {BOATS.map(([x, y, w], i) => (
          <g key={`boat${i}`} className="boat" style={{ animationDelay: `${i * -2}s` }}>
            {boat(x, y, w).map((l, j) => <path key={j} d={l.d} pathLength={1} className={l.gold ? "stroke gold" : "stroke"} style={{ animationDelay: `${l.delay}s`, strokeWidth: l.bold ? 1.8 : undefined }} />)}
          </g>
        ))}
        {DIYAS.map(([x, y], i) => (
          <g key={`d${i}`} className="boat" style={{ animationDelay: `${i * -0.7}s`, animationDuration: `${4 + (i % 3)}s` }}>
            <ellipse className="glow" cx={x} cy={y - 9} rx="12" ry="12" style={{ animationDelay: `${i * 0.3}s` }} />
            <path className="stroke gold" pathLength={1} style={{ animationDelay: `${2.4 + i * 0.05}s`, strokeWidth: 1.6 }} d={`M${x - 10} ${y} q10 9 20 0 z`} />
            <path className="flame" style={{ animationDelay: `${i * 0.17}s` }} d={`M${x} ${y - 1} q-5 -6 0 -15 q5 9 0 15 z`} />
          </g>
        ))}
        {MARIGOLDS.map(([x, y], i) => (
          <g key={`m${i}`} className="boat" style={{ animationDelay: `${i * -1.3}s` }}>
            {Array.from({ length: 6 }, (_, k) => (
              <circle key={k} className="marigold" cx={x + Math.cos((k * Math.PI) / 3) * 3.2} cy={y + Math.sin((k * Math.PI) / 3) * 2} r="2.4" />
            ))}
          </g>
        ))}
      </g>
    </>
  );
});

const HIDDEN = /^\/(documents|precedents)/;

export default function GhatScene({ enabled }: { enabled: boolean }) {
  const { pathname } = useLocation();
  if (!enabled || HIDDEN.test(pathname)) return null;
  return (
    <svg className="ghats" viewBox="0 0 1600 400" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
      <Scene />
    </svg>
  );
}
