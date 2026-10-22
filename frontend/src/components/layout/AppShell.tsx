import { ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { FileUp } from "lucide-react";
import toast from "react-hot-toast";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import CommandPalette from "../CommandPalette";
import HelpDrawer from "../HelpDrawer";
import UploadDialog from "../UploadDialog";
import Emblem from "../Emblem";
import GhatScene from "../GhatScene";
import { DeskContext, usePreference, useTheme } from "../../lib/theme";
import { asItem, dropHasFolder, filesFromDrop } from "../../lib/drop";
import type { UploadItem } from "../../api/aagam";
import { ConfirmProvider } from "../dialogs";

const typing = (e: KeyboardEvent) => {
  const el = e.target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
};

export default function AppShell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const [theme, setTheme] = useTheme();
  const [art, setArt] = usePreference("aagam.art", true);
  const [palette, setPalette] = useState(false);
  const [help, setHelp] = useState(false);
  const [upload, setUpload] = useState<{ open: boolean; files: UploadItem[] }>({ open: false, files: [] });
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);

  const openUpload = useCallback(
    (files: (File | UploadItem)[] = []) => setUpload({ open: true, files: files.map((f) => (f instanceof File ? asItem(f) : f)) }),
    []
  );
  const closeHelp = useCallback(() => setHelp(false), []);
  const closeUpload = useCallback(() => setUpload({ open: false, files: [] }), []);
  const desk = useMemo(() => ({ theme, openUpload, openHelp: () => setHelp(true), openPalette: () => setPalette(true), art, setArt }), [theme, openUpload, art, setArt]);

  // Ctrl+K finds anything; "?" opens help for this page.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((open) => !open);
      } else if (e.key === "?" && !typing(e)) {
        e.preventDefault();
        setHelp((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Files dragged in from Explorer can be dropped anywhere.
  useEffect(() => {
    const hasFiles = (e: DragEvent) => Array.from(e.dataTransfer?.types ?? []).includes("Files");
    const enter = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current += 1;
      setDragging(true);
    };
    const leave = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      depth.current = Math.max(0, depth.current - 1);
      if (depth.current === 0) setDragging(false);
    };
    const over = (e: DragEvent) => hasFiles(e) && e.preventDefault();
    const drop = (e: DragEvent) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth.current = 0;
      setDragging(false);
      // A drop on the upload box itself is handled there.
      if ((e.target as HTMLElement)?.closest?.("[role=dialog]") || !e.dataTransfer) return;
      if (dropHasFolder(e.dataTransfer)) {
        // A folder: walk into it, keeping where each file sat, so the library can sort them by folder.
        const reading = toast.loading("Looking through the folder…");
        filesFromDrop(e.dataTransfer)
          .then((items) => {
            toast.dismiss(reading);
            if (items.length) openUpload(items);
            else toast.error("There were no files in that folder.");
          })
          .catch(() => {
            toast.dismiss(reading);
            toast.error("That folder couldn't be read. Try Library → Add a folder.");
          });
        return;
      }
      const files = Array.from(e.dataTransfer.files ?? []);
      if (files.length) openUpload(files);
    };
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [openUpload]);

  return (
    <DeskContext.Provider value={desk}>
      <ConfirmProvider>
      <div className="flex h-screen overflow-hidden backdrop">
        <Sidebar />
        <div className="flex flex-col flex-1 min-w-0 relative">
          {theme === "banaras" ? <GhatScene enabled={art} /> : <Emblem enabled={art} />}
          <TopBar theme={theme} setTheme={setTheme} />
          <main className="flex-1 overflow-auto relative z-10">
            <div key={pathname} className="page-enter h-full">{children}</div>
          </main>
        </div>
        <CommandPalette open={palette} onClose={() => setPalette(false)} setTheme={setTheme} />
        <HelpDrawer open={help} onClose={closeHelp} />
        <UploadDialog open={upload.open} initial={upload.files} onClose={closeUpload} />
        {dragging && !upload.open && (
          <div className="fixed inset-0 z-[60] pointer-events-none flex items-center justify-center fade-in">
            <div className="absolute inset-3 rounded-3xl border-2 border-dashed border-accent-brand bg-accent-brand/5 backdrop-blur-[1px]" />
            <div className="relative card px-8 py-6 text-center pop-in">
              <FileUp size={28} className="mx-auto text-accent-brand mb-2" />
              <p className="display text-lg font-semibold">Drop to add to the library</p>
              <p className="text-sm text-text-muted mt-1">Files or whole folders. You can choose the client and type next.</p>
            </div>
          </div>
        )}
      </div>
      </ConfirmProvider>
    </DeskContext.Provider>
  );
}
