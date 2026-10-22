import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

/**
 * The art behind the desk: line drawings that draw themselves, hold, and give way to the next.
 * Justice with her scales, the ledger, the company's seal, and the minute book with its quill.
 * It follows the work (the ledger on Financials, the seal on People and companies, the minute book on Work)
 * and moves on by itself every so often. Faint, behind everything, and still when Windows asks for less motion.
 */

type Shape =
  | { t: "p"; d: string; bold?: boolean }
  | { t: "c"; cx: number; cy: number; r: number; bold?: boolean }
  | { t: "text"; x: number; y: number; s: string; size: number; italic?: boolean; anchor?: "start" | "middle" | "end"; rotate?: number }
  | { t: "ring"; cx: number; cy: number; r: number; s: string; size: number }
  | { t: "wash"; d: string };

const rows = (from: number, to: number, step: number, line: (y: number) => string) => {
  const out: Shape[] = [];
  for (let y = from; y <= to; y += step) out.push({ t: "p", d: line(y) });
  return out;
};

const JUSTICE: Shape[] = [
  // Head, hair and the blindfold
  { t: "c", cx: 262, cy: 98, r: 24 },
  { t: "c", cx: 262, cy: 69, r: 9 },
  { t: "p", d: "M240 90 C248 74 276 74 284 90" },
  { t: "p", d: "M238 92 C254 99 270 99 286 92 L286 102 C270 109 254 109 238 102 Z", bold: true },
  { t: "p", d: "M286 96 C300 100 308 112 312 128" },
  { t: "p", d: "M286 100 C296 110 300 124 297 138" },
  { t: "p", d: "M262 109 L260 114 L263 115" },
  { t: "p", d: "M257 118 C260 120 264 120 267 118" },
  // Neck, shoulders, the robe
  { t: "p", d: "M254 121 L253 132 M270 121 L271 132" },
  { t: "p", d: "M253 132 C238 134 228 138 222 146" },
  { t: "p", d: "M271 132 C286 134 296 138 302 146" },
  { t: "p", d: "M246 137 C254 151 270 151 278 137" },
  { t: "p", d: "M222 146 C214 210 214 260 212 300 C208 380 200 440 188 500" },
  { t: "p", d: "M302 146 C310 210 312 260 314 300 C318 380 326 440 338 500" },
  { t: "p", d: "M188 500 C220 512 300 514 338 500" },
  { t: "p", d: "M216 236 C240 246 286 246 310 236 M216 244 C240 254 286 254 310 244" },
  { t: "p", d: "M240 152 C238 182 236 212 238 238 M284 152 C286 182 288 212 286 238" },
  { t: "p", d: "M236 254 C232 330 222 420 208 504" },
  { t: "p", d: "M262 256 C262 340 260 430 258 511" },
  { t: "p", d: "M288 254 C294 330 304 420 318 505" },
  { t: "p", d: "M249 300 C247 380 240 450 233 507 M276 300 C280 380 286 450 292 509" },
  { t: "p", d: "M236 508 C240 516 252 516 256 510 M270 510 C274 517 286 517 290 509" },
  // The arm raised, holding the scales
  { t: "p", d: "M224 144 C206 130 188 120 170 112 C156 106 146 100 140 94" },
  { t: "p", d: "M220 164 C204 150 188 140 174 132 C160 124 150 116 144 106" },
  { t: "p", d: "M206 138 C200 160 206 176 218 184" },
  { t: "p", d: "M136 92 C132 98 136 106 144 106 C150 104 150 96 144 92 C141 90 138 90 136 92 Z" },
  { t: "p", d: "M140 106 L140 114 M131 114 C133 107 147 107 149 114" },
  { t: "p", d: "M88 114 L188 114", bold: true },
  { t: "c", cx: 88, cy: 114, r: 3 },
  { t: "c", cx: 188, cy: 114, r: 3 },
  { t: "p", d: "M88 114 L70 176 M88 114 L106 176" },
  { t: "p", d: "M188 114 L170 176 M188 114 L206 176" },
  { t: "p", d: "M64 176 C74 194 102 194 112 176 Z" },
  { t: "p", d: "M164 176 C174 194 202 194 212 176 Z" },
  // The other arm, the sword pointing down
  { t: "p", d: "M302 146 C316 176 322 206 324 236" },
  { t: "p", d: "M296 168 C302 196 306 220 308 240" },
  { t: "p", d: "M306 240 C304 250 312 256 320 254 C328 252 328 242 322 238 C316 236 309 236 306 240 Z" },
  { t: "c", cx: 314, cy: 224, r: 4 },
  { t: "p", d: "M316 238 L315 228" },
  { t: "p", d: "M300 259 L334 253", bold: true },
  { t: "p", d: "M314 257 L340 392 L346 405 L349 390 L324 255 M320 262 L343 388" },
  // The plinth
  { t: "p", d: "M170 513 L356 513 M178 513 L178 530 L348 530 L348 513" },
  { t: "p", d: "M160 530 L366 530 L366 545 L160 545 Z" },
  { t: "text", x: 263, y: 525, s: "FIAT JUSTITIA", size: 9, anchor: "middle" },
];

const LEDGER: Shape[] = [
  { t: "wash", d: "M56 184 C110 170 168 174 210 196 C252 174 310 170 364 184 L364 438 C310 424 252 428 210 448 C168 428 110 424 56 438 Z" },
  { t: "p", d: "M44 196 L44 452 C120 438 170 444 210 462 C250 444 300 438 376 452 L376 196", bold: true },
  { t: "p", d: "M56 184 C110 170 168 174 210 196 L210 448 C168 428 110 424 56 438 Z" },
  { t: "p", d: "M210 196 C252 174 310 170 364 184 L364 438 C310 424 252 428 210 448 Z" },
  { t: "p", d: "M50 190 L50 446 M370 190 L370 446" },
  ...rows(232, 412, 22, (y) => `M66 ${y} Q136 ${y - 9} 202 ${y + 7}`),
  ...rows(232, 412, 22, (y) => `M218 ${y + 7} Q284 ${y - 9} 354 ${y}`),
  { t: "p", d: "M98 202 L98 430 M162 196 L162 434 M258 196 L258 434 M322 202 L322 430" },
  { t: "text", x: 128, y: 214, s: "Dr.", size: 15, italic: true, anchor: "middle" },
  { t: "text", x: 184, y: 214, s: "₹", size: 15, anchor: "middle" },
  { t: "text", x: 290, y: 214, s: "Cr.", size: 15, italic: true, anchor: "middle" },
  { t: "text", x: 342, y: 214, s: "₹", size: 15, anchor: "middle" },
  ...[["To Capital", "10,00,000"], ["To Loans", "25,40,000"], ["To Creditors", "8,75,500"], ["To Reserves", "4,12,300"]].flatMap(
    ([a, b], i): Shape[] => [
      { t: "text", x: 102, y: 248 + i * 22, s: a, size: 9.5, italic: true },
      { t: "text", x: 198, y: 251 + i * 22, s: b, size: 9.5, anchor: "end" },
    ]
  ),
  ...[["By Plant", "18,60,000"], ["By Stock", "9,10,800"], ["By Debtors", "12,04,000"], ["By Bank", "8,53,000"]].flatMap(
    ([a, b], i): Shape[] => [
      { t: "text", x: 262, y: 251 + i * 22, s: a, size: 9.5, italic: true },
      { t: "text", x: 352, y: 248 + i * 22, s: b, size: 9.5, anchor: "end" },
    ]
  ),
  { t: "p", d: "M166 352 L200 358 M166 356 L200 362 M320 354 L354 348 M320 358 L354 352" },
  { t: "text", x: 198, y: 374, s: "48,27,800", size: 10, anchor: "end" },
  { t: "text", x: 352, y: 370, s: "48,27,800", size: 10, anchor: "end" },
  // The pen, and the ribbon
  { t: "p", d: "M296 476 L384 388 L393 397 L305 485 Z" },
  { t: "p", d: "M296 476 L282 494 L305 485 M360 412 L372 400" },
  { t: "p", d: "M206 450 C204 478 200 498 204 520 L210 510 L216 520 C220 498 216 478 214 450" },
];

const SEAL: Shape[] = [
  { t: "c", cx: 210, cy: 236, r: 132, bold: true },
  { t: "c", cx: 210, cy: 236, r: 120 },
  { t: "c", cx: 210, cy: 236, r: 78 },
  { t: "c", cx: 210, cy: 236, r: 72 },
  { t: "ring", cx: 210, cy: 236, r: 92, s: "BY ORDER OF THE BOARD  ✦  COMPANY SECRETARY  ✦  COMMON SEAL  ✦  ", size: 15 },
  { t: "p", d: "M162 238 C172 206 188 214 184 234 C180 258 198 222 206 230 C214 240 216 256 224 236 C230 222 238 232 242 240 C248 252 256 232 262 226" },
  { t: "p", d: "M160 262 L262 262" },
  { t: "text", x: 210, y: 282, s: "Company Secretary", size: 11, italic: true, anchor: "middle" },
  { t: "text", x: 210, y: 300, s: "AAGAM", size: 8.5, anchor: "middle" },
  // "Certified true copy" stamped across the foot
  { t: "p", d: "M100 418 L320 386 L328 440 L108 472 Z", bold: true },
  { t: "p", d: "M108 424 L314 394 L320 434 L114 464 Z" },
  { t: "text", x: 214, y: 438, s: "CERTIFIED TRUE COPY", size: 19, anchor: "middle", rotate: -8.2 },
];

const MINUTES: Shape[] = [
  { t: "wash", d: "M110 128 L310 128 L310 424 L110 424 Z" },
  { t: "p", d: "M110 128 L110 424 M310 128 L310 424", bold: true },
  { t: "p", d: "M98 118 C98 104 322 104 322 118 C322 132 98 132 98 118 Z" },
  { t: "p", d: "M98 118 C88 118 86 104 96 102 C104 101 106 110 100 112" },
  { t: "p", d: "M322 118 C332 118 334 104 324 102 C316 101 314 110 320 112" },
  { t: "p", d: "M98 432 C98 418 322 418 322 432 C322 446 98 446 98 432 Z" },
  { t: "p", d: "M98 432 C88 432 86 446 96 448 C104 449 106 440 100 438" },
  { t: "p", d: "M322 432 C332 432 334 446 324 448 C316 449 314 440 320 438" },
  { t: "text", x: 210, y: 162, s: "MINUTES OF THE MEETING", size: 12, anchor: "middle" },
  { t: "text", x: 210, y: 178, s: "of the Board of Directors", size: 9.5, italic: true, anchor: "middle" },
  { t: "text", x: 132, y: 206, s: "RESOLVED THAT", size: 10 },
  ...[0, 1, 2, 3, 4, 5, 6, 7, 8].map((i): Shape => ({ t: "p", d: `M132 ${222 + i * 20} L${[288, 270, 290, 250, 286, 262, 290, 240, 278][i]} ${222 + i * 20}` })),
  { t: "p", d: "M220 404 C228 390 236 398 234 406 C232 414 244 394 252 398 C258 402 260 410 268 400" },
  { t: "text", x: 244, y: 418, s: "Chairman", size: 8.5, italic: true, anchor: "middle" },
  // The quill and the inkpot
  { t: "p", d: "M304 470 C334 400 362 330 394 248", bold: true },
  { t: "p", d: "M304 470 C320 408 334 356 358 302 C370 274 384 256 394 248 C390 270 382 302 368 332 C348 382 326 430 304 470 Z" },
  { t: "p", d: "M346 330 L330 322 M356 304 L342 294 M338 356 L324 350 M366 286 L354 276 M352 342 L366 344 M362 316 L376 318 M344 368 L358 372" },
  { t: "p", d: "M268 472 L336 472 L346 504 L258 504 Z" },
  { t: "p", d: "M280 472 L282 460 L322 460 L324 472" },
];

const MOTIFS = [JUSTICE, LEDGER, SEAL, MINUTES];
const FOR_PAGE: [RegExp, number][] = [[/^\/financials/, 1], [/^\/(entities|notes)/, 2], [/^\/work/, 3], [/^\/(search|precedents|calculators|due|help|library)?$/, 0]];
// Reading pages keep a clean page behind the text.
const HIDDEN = /^\/(documents|precedents)/;
const EVERY = 22_000;

function preferred(path: string): number | null {
  for (const [pattern, index] of FOR_PAGE) if (pattern.test(path)) return index;
  return null;
}

export default function Emblem({ enabled }: { enabled: boolean }) {
  const { pathname } = useLocation();
  const [state, setState] = useState(() => ({ current: preferred(pathname) ?? 0, leaving: null as number | null, round: 0 }));
  const go = (next: (now: number) => number) =>
    setState((s) => {
      const n = next(s.current);
      return n === s.current ? s : { current: n, leaving: s.current, round: s.round + 1 };
    });

  // Follow the page she is on.
  useEffect(() => {
    const p = preferred(pathname);
    if (p !== null) go(() => p);
  }, [pathname]);

  // Move on by itself, and let the old drawing fade away.
  useEffect(() => {
    const next = window.setTimeout(() => go((now) => (now + 1) % MOTIFS.length), EVERY);
    const tidy = window.setTimeout(() => setState((s) => (s.leaving === null ? s : { ...s, leaving: null })), 1800);
    return () => {
      window.clearTimeout(next);
      window.clearTimeout(tidy);
    };
  }, [state.round]);

  if (!enabled || HIDDEN.test(pathname)) return null;
  const { current, leaving, round } = state;
  return (
    <svg className="emblem" viewBox="0 0 420 560" aria-hidden="true">
      {leaving !== null && <Motif key={`out-${round}`} shapes={MOTIFS[leaving]} leaving id={`l${round}`} />}
      <Motif key={`in-${round}`} shapes={MOTIFS[current]} id={`c${round}`} />
    </svg>
  );
}

function Motif({ shapes, leaving, id }: { shapes: Shape[]; leaving?: boolean; id: string }) {
  // Leaving motifs are already drawn; only the arriving one draws itself, stroke by stroke.
  const delay = (i: number) => ({ animationDelay: leaving ? "0ms" : `${i * 55}ms`, animationDuration: leaving ? "1ms" : undefined });
  const inkDelay = (i: number) => ({ animationDelay: leaving ? "0ms" : `${1400 + i * 30}ms`, animationDuration: leaving ? "1ms" : undefined });
  return (
    <g className={leaving ? "motif leaving" : "motif"}>
      {shapes.map((s, i) => {
        switch (s.t) {
          case "p":
            return <path key={i} d={s.d} pathLength={1} className={s.bold ? "stroke bold" : "stroke"} style={delay(i)} />;
          case "c":
            return <circle key={i} cx={s.cx} cy={s.cy} r={s.r} pathLength={1} className={s.bold ? "stroke bold" : "stroke"} style={delay(i)} />;
          case "wash":
            return <path key={i} d={s.d} className="wash" style={inkDelay(0)} />;
          case "text":
            return (
              <text key={i} x={s.x} y={s.y} className="ink" fontSize={s.size} textAnchor={s.anchor ?? "start"}
                fontFamily="Cambria, Georgia, serif" fontStyle={s.italic ? "italic" : undefined} letterSpacing={s.size > 11 ? 1.5 : 0.3}
                transform={s.rotate ? `rotate(${s.rotate} ${s.x} ${s.y})` : undefined} style={inkDelay(i)}>
                {s.s}
              </text>
            );
          case "ring": {
            const path = `M${s.cx - s.r} ${s.cy} a${s.r} ${s.r} 0 1 1 ${2 * s.r} 0 a${s.r} ${s.r} 0 1 1 ${-2 * s.r} 0`;
            return (
              <g key={i}>
                <defs><path id={`ring-${id}`} d={path} /></defs>
                <text className="ink" fontSize={s.size} fontFamily="Cambria, Georgia, serif" letterSpacing={2} style={inkDelay(i)}>
                  <textPath href={`#ring-${id}`} textLength={Math.round(2 * Math.PI * s.r) - 6} lengthAdjust="spacing">{s.s}</textPath>
                </text>
              </g>
            );
          }
        }
      })}
    </g>
  );
}
