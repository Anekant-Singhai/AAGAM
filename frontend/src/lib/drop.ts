import type { UploadItem } from "../api/aagam";

// Files Windows and Office leave beside real ones: hidden files, Word's "~$" lock files, folder settings.
const JUNK = /^(\.|~\$)|^(desktop\.ini|thumbs\.db)$/i;

/** A file's place inside a folder she dropped or chose ("Acme/2024-25/notice.pdf"), or "" for a loose file. */
export function relativePath(file: File): string {
  const raw = (file as File & { relativePath?: string; path?: string }).relativePath
    || (file as File & { path?: string }).path
    || file.webkitRelativePath
    || "";
  const clean = raw.replace(/\\/g, "/").replace(/^\.?\/+/, "");
  return clean.includes("/") ? clean : "";
}

export const asItem = (file: File): UploadItem => ({ file, path: relativePath(file) });

export function isJunk(name: string): boolean {
  return JUNK.test(name);
}

/** True when a drop holds at least one folder (only Chrome and Edge can tell). */
export function dropHasFolder(data: DataTransfer | null): boolean {
  return Array.from(data?.items ?? []).some((item) => item.kind === "file" && item.webkitGetAsEntry?.()?.isDirectory);
}

/**
 * Every file in what was dropped, walking into folders and keeping each file's place inside them.
 * The entries are taken during the drop itself (the browser forgets them once the drop is over) and read afterwards.
 */
export async function filesFromDrop(data: DataTransfer): Promise<UploadItem[]> {
  const entries = Array.from(data.items)
    .filter((item) => item.kind === "file")
    .map((item) => item.webkitGetAsEntry?.())
    .filter((entry): entry is FileSystemEntry => Boolean(entry));
  const out: UploadItem[] = [];
  for (const entry of entries) await walk(entry, out);
  return out;
}

async function walk(entry: FileSystemEntry, out: UploadItem[]): Promise<void> {
  if (isJunk(entry.name)) return;
  if (entry.isFile) {
    try {
      const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject));
      const path = entry.fullPath.replace(/^\/+/, "");
      out.push({ file, path: path.includes("/") ? path : "" });
    } catch {
      /* a file Windows won't let the browser read: leave it out */
    }
    return;
  }
  if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    // readEntries hands back a hundred or so at a time; ask until it has no more.
    for (;;) {
      const batch = await new Promise<FileSystemEntry[]>((resolve) => reader.readEntries(resolve, () => resolve([])));
      if (!batch.length) break;
      for (const child of batch) await walk(child, out);
    }
  }
}
