import { Fragment, ReactNode } from "react";
import { format, parseISO } from "date-fns";

export function crore(rupees: number | null | undefined): string {
  if (rupees === null || rupees === undefined) return "";
  const cr = rupees / 10_000_000;
  if (cr >= 1) return `₹${cr.toLocaleString("en-IN", { maximumFractionDigits: 2 })} crore`;
  return `₹${rupees.toLocaleString("en-IN")}`;
}

export function rupees(value: string): string {
  const n = Number(value);
  return Number.isFinite(n) ? `₹${n.toLocaleString("en-IN")}` : value;
}

export function day(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return format(parseISO(iso), "d MMM yyyy");
  } catch {
    return iso;
  }
}

/** Passages from search come with matches in [[double brackets]]; show them highlighted. */
export function Marked({ text }: { text: string }) {
  const parts = text.split(/(\[\[.*?\]\])/g);
  return (
    <>
      {parts.map((part, i) =>
        part.startsWith("[[") && part.endsWith("]]") ? <mark key={i}>{part.slice(2, -2)}</mark> : <Fragment key={i}>{part}</Fragment>
      )}
    </>
  );
}

/** Highlight her search words in full page text (case-insensitive, whole words or prefixes). */
export function highlightWords(text: string, query: string): ReactNode {
  const words = query.match(/[\p{L}\p{N}]{2,}/gu);
  if (!words?.length) return text;
  const pattern = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
  return text.split(pattern).map((part, i) => (i % 2 === 1 ? <mark key={i}>{part}</mark> : <Fragment key={i}>{part}</Fragment>));
}

export function byWhom(by: string | null): string {
  if (!by) return "";
  if (by === "her") return "Written by you";
  if (by === "claude") return "By Claude";
  if (by.startsWith("local:")) return `By local AI (${by.slice(6)})`;
  return by;
}

export function titleCase(slug: string): string {
  return slug.replace(/[-_]/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** A figure from the statements in their own unit (lakhs, crore…), brackets for negatives as accountants write them. */
export function inUnit(rupees: number | null | undefined, factor = 1): string {
  if (rupees === null || rupees === undefined) return "—";
  const v = rupees / factor;
  const digits = factor === 1 ? 0 : 2;
  const s = Math.abs(v).toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return v < 0 ? `(${s})` : s;
}

/** "3 days ago", "today": for when something was last touched. */
export function ago(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso.includes("T") || iso.includes(" ") ? iso.replace(" ", "T") + (iso.endsWith("Z") ? "" : "Z") : iso);
  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000);
  if (Number.isNaN(days)) return iso;
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  return day(iso.slice(0, 10));
}

/** A size on disk, as Windows shows it: "820 KB", "1.4 MB", "2.1 GB". */
export function bytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "";
  if (n < 1024) return `${n} bytes`;
  const units = ["KB", "MB", "GB", "TB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toLocaleString("en-IN", { maximumFractionDigits: v < 10 ? 1 : 0 })} ${units[i]}`;
}

/** "3 files", "1 file". */
export function count(n: number, one: string, many = `${one}s`): string {
  return `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;
}

/** What she can do about files AAGAM can't read yet, by their extension. */
export function skippedHint(ext: string, n: number): string {
  const what = `${count(n, `${ext} file`)} can't be read`;
  const fix: Record<string, string> = {
    ".doc": "save them as .docx in Word", ".ppt": "save them as .pptx in PowerPoint", ".zip": "unzip them first", ".rar": "unzip them first",
    ".7z": "unzip them first", ".xlsb": "save them as .xlsx in Excel", ".odt": "save them as .docx", ".pages": "export them as PDF or Word",
  };
  return fix[ext.toLowerCase()] ? `${what}: ${fix[ext.toLowerCase()]}` : `${what} yet`;
}

/** Why a document is filed under its client, from what the server says: "its CIN …", "the folder “Acme”", "set by her". */
export function clientReason(why?: string | null): string | undefined {
  if (!why) return undefined;
  return why === "set by her" ? "You chose this client" : `Filed under this client from ${why}`;
}

/** A month as she would say it: "April 2024". */
export function month(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    return format(parseISO(iso.slice(0, 7) + "-01"), "MMMM yyyy");
  } catch {
    return iso.slice(0, 7);
  }
}

/** Days from today to a date: negative when it has passed. */
export function daysTo(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const target = new Date(`${iso.slice(0, 10)}T00:00:00`);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86_400_000);
}
