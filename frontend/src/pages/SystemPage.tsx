import { ReactNode, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, Archive, CheckCircle2, ChevronDown, FolderOpen, HardDrive, HeartPulse, KeyRound, LifeBuoy, Loader2, PackageX, RefreshCw, Sparkles, Wrench, XCircle,
} from "lucide-react";
import toast from "react-hot-toast";
import clsx from "clsx";
import { aagam } from "../api/aagam";
import { missing } from "../api/client";
import { ago, day } from "../lib/format";
import type { HealthCheck, SystemInfo, SystemTask } from "../types";
import { PageHeader, PageSkeleton } from "../components/ui";
import { Modal, useConfirm } from "../components/dialogs";
import { UpdatingOverlay, useSystem } from "../components/Updates";

const ACTIONS: Record<string, string> = {
  local_ai: "Install local AI",
  claude: "Connect Claude Desktop",
  shortcuts: "Put the shortcuts back",
  reinstall: "Repair AAGAM",
};
const short = (commit: string | null | undefined) => (commit ? commit.slice(0, 7) : "");

/** Updates & health: keep AAGAM up to date, check this computer, repair a part, or remove AAGAM. */
export default function SystemPage() {
  const { data, error, refetch } = useSystem(true);
  const [params, setParams] = useSearchParams();
  const [updating, setUpdating] = useState<{ version: string; commit: string | null } | null>(null);
  const [removing, setRemoving] = useState(false);
  const confirm = useConfirm();
  const queryClient = useQueryClient();

  const failed = useCallback((message: string) => {
    setUpdating(null);
    toast.error(`The update didn't go through: ${message}`, { duration: 10_000 });
    queryClient.invalidateQueries({ queryKey: ["system"] });
  }, [queryClient]);

  const update = useCallback(async (info: SystemInfo) => {
    const ok = await confirm({
      title: "Update AAGAM now?",
      body: "AAGAM closes for a minute while the new version is put in place, then opens again by itself.",
      items: ["Your documents, clients, notes and work are not touched", "If anything goes wrong, the version you have now is put back", "Close Claude Desktop first if it is open; restart it afterwards"],
      action: "Update now",
    });
    if (!ok) return;
    try {
      await aagam.applyUpdate();
      setUpdating({ version: info.version, commit: info.commit });
    } catch (e) {
      toast.error((e as Error).message);
    }
  }, [confirm]);

  // From the banner ("Update now") or the command palette ("Check for updates").
  useEffect(() => {
    const ask = params.get("update") === "now";
    const check = params.get("check") === "1";
    if (!data || (!ask && !check)) return;
    const next = new URLSearchParams(params);
    next.delete("update");
    next.delete("check");
    setParams(next, { replace: true });
    if (ask && data.updates.available) update(data);
    if (check) aagam.checkUpdates().then(() => refetch()).catch((e: Error) => toast.error(e.message));
  }, [data, params]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error) {
    return (
      <div className="px-8 py-6 max-w-4xl">
        <PageHeader icon={<HeartPulse size={19} />} title="Updates & health" />
        <p className="text-sm text-text-muted">{missing(error) ? "This copy of AAGAM can't update itself yet. Install the latest AAGAM once with install.cmd; after that, updates come here." : (error as Error).message}</p>
      </div>
    );
  }
  if (!data) return <PageSkeleton rows={4} />;

  return (
    <div className="px-8 py-6 max-w-4xl space-y-5">
      <PageHeader
        icon={<HeartPulse size={19} />}
        title="Updates & health"
        subtitle="Keep AAGAM up to date, check this computer, back up your work, or remove AAGAM."
      />
      <ThisCopy info={data} />
      <Updates info={data} onUpdate={() => update(data)} />
      <Health />
      <Care />
      <Uninstall onStarted={() => setRemoving(true)} />
      {updating && <UpdatingOverlay from={updating} onFailed={failed} />}
      {removing && <Removed />}
    </div>
  );
}

function Card({ title, icon, children, actions }: { title: string; icon: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card p-5">
      <div className="flex items-center gap-2.5 mb-3">
        <span className="w-8 h-8 rounded-lg bg-accent-brand/10 text-accent-brand flex items-center justify-center shrink-0">{icon}</span>
        <h2 className="font-semibold flex-1">{title}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}

function ThisCopy({ info }: { info: SystemInfo }) {
  return (
    <Card title="This copy of AAGAM" icon={<HardDrive size={16} />}>
      <dl className="grid grid-cols-[150px_1fr] gap-y-1.5 text-sm">
        <dt className="text-text-muted">Version</dt>
        <dd>AAGAM {info.version}{info.commit && <span className="font-mono text-xs text-text-muted"> · {short(info.commit)}</span>}</dd>
        {info.installed_at && (<><dt className="text-text-muted">Installed or updated</dt><dd>{day(info.installed_at.slice(0, 10))}</dd></>)}
        {info.app_folder && (<><dt className="text-text-muted">The program</dt><dd className="font-mono text-xs break-all pt-0.5">{info.app_folder}</dd></>)}
        {info.data_folder && (<><dt className="text-text-muted">Your data</dt><dd className="font-mono text-xs break-all pt-0.5">{info.data_folder}</dd></>)}
        <dt className="text-text-muted">Updates from</dt>
        <dd>
          {info.mode === "none" ? "Nowhere yet: this copy wasn't installed from GitHub."
            : info.mode === "git" ? `GitHub, through Git${info.repo ? ` (${info.repo}${info.branch ? `, ${info.branch}` : ""})` : ""}`
            : `GitHub${info.repo ? ` (${info.repo}${info.branch ? `, ${info.branch}` : ""})` : ""}`}
        </dd>
      </dl>
    </Card>
  );
}

function Updates({ info, onUpdate }: { info: SystemInfo; onUpdate: () => void }) {
  const queryClient = useQueryClient();
  const [checking, setChecking] = useState(false);
  const [advanced, setAdvanced] = useState(false);
  const u = info.updates;
  const check = async () => {
    setChecking(true);
    try {
      const state = await aagam.checkUpdates();
      queryClient.setQueryData<SystemInfo>(["system"], (old) => (old ? { ...old, updates: state } : old));
      if (!state.available && !state.error) toast.success("AAGAM is up to date.");
      if (state.error) toast.error(state.error);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setChecking(false);
    }
  };
  const setAuto = async (on: boolean) => {
    try {
      queryClient.setQueryData(["system"], await aagam.updateSettings({ auto_update: on }));
      toast.success(on ? "New versions will be put in place by themselves while AAGAM isn't in use." : "AAGAM will wait for you to press Update now.");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const setStart = async (on: boolean) => {
    try {
      queryClient.setQueryData(["system"], await aagam.updateSettings({ autostart: on }));
      toast.success(on ? "AAGAM will start in the background when you sign in to Windows." : "AAGAM will start only when you open it.");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const busy = checking || ["checking", "downloading", "applying"].includes(u.status);
  return (
    <Card
      title="Updates"
      icon={<Sparkles size={16} />}
      actions={info.mode !== "none" && (
        <button className="btn py-1" onClick={check} disabled={busy}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Check now
        </button>
      )}
    >
      {u.available && u.latest ? (
        <div className="rounded-xl border border-accent-brand/30 bg-accent-brand/5 p-4 mb-3">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex-1 min-w-0">
              <p className="font-medium">A new version is ready{u.latest.version && u.latest.version !== info.version ? `: AAGAM ${u.latest.version}` : ""}</p>
              <p className="text-xs text-text-muted">
                {u.latest.date ? `Published ${day(u.latest.date.slice(0, 10))} · ` : ""}<span className="font-mono">{short(u.latest.commit)}</span>
              </p>
            </div>
            <button className="btn btn-primary" onClick={onUpdate} disabled={busy}><RefreshCw size={14} /> Update now</button>
          </div>
          {u.changes.length > 0 && (
            <>
              <p className="label mt-3 mb-1">What's new</p>
              <ul className="text-sm space-y-1 max-h-56 overflow-auto">
                {u.changes.map((c) => (
                  <li key={c.commit} className="flex gap-2">
                    <span className="text-accent-brand mt-0.5">•</span>
                    <span className="min-w-0">
                      <span className="block">{c.message.split("\n")[0]}</span>
                      {c.date && <span className="text-xs text-text-muted">{day(c.date.slice(0, 10))}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      ) : (
        <p className="text-sm text-text-secondary mb-3 flex items-center gap-2">
          {u.status === "failed" ? <AlertTriangle size={15} className="text-accent-amber" /> : <CheckCircle2 size={15} className="text-accent-green" />}
          {info.mode === "none"
            ? "Install AAGAM with install.cmd (from GitHub) and it will find and put in place new versions by itself."
            : u.status === "failed" && u.error ? `The last check didn't work: ${u.error}`
            : u.checked_at ? `AAGAM is up to date. Last checked ${ago(u.checked_at)}.` : "Not checked yet."}
        </p>
      )}
      {u.needs_token && (
        <p className="text-sm text-accent-amber mb-3 flex items-start gap-2">
          <KeyRound size={15} className="mt-0.5 shrink-0" /> The repository on GitHub is private. Add an access key under More settings, below.
        </p>
      )}
      {u.last_update && (
        <div className={clsx("text-sm rounded-lg px-3 py-2 mb-3", u.last_update.ok ? "bg-accent-green/10" : "bg-accent-red/10")}>
          <p className="flex items-center gap-2">
            {u.last_update.ok ? <CheckCircle2 size={14} className="text-accent-green" /> : <XCircle size={14} className="text-accent-red" />}
            {u.last_update.ok ? "Updated" : "The last update didn't go through"} {ago(u.last_update.at)}
            {u.last_update.from && u.last_update.to && <span className="font-mono text-xs text-text-muted">({short(u.last_update.from)} → {short(u.last_update.to)})</span>}
          </p>
          {u.last_update.error && <p className="text-xs text-text-secondary mt-1">{u.last_update.error}</p>}
          {u.last_update.notes.length > 0 && (
            <ul className="text-xs text-text-secondary mt-1 list-disc pl-5">{u.last_update.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
          )}
        </div>
      )}
      {info.mode === "archive" && (
        <Switch on={info.auto_update} onChange={setAuto} label="Install updates by themselves"
          hint="A new version is put in place once AAGAM has been left alone for 20 minutes, never while you are working. Until then, Update now does it." />
      )}
      {info.autostart !== undefined && info.mode !== "git" && (
        <Switch on={Boolean(info.autostart)} onChange={setStart} label="Start AAGAM when I sign in to Windows"
          hint="It waits quietly in the background, so it opens at once and keeps reading watched folders. Windows lists it in Task Manager, Startup apps." />
      )}
      <button className="mt-4 text-xs text-text-muted hover:text-text-primary flex items-center gap-1" onClick={() => setAdvanced(!advanced)} aria-expanded={advanced}>
        <ChevronDown size={13} className={clsx("transition-transform", advanced && "rotate-180")} /> More settings
      </button>
      {advanced && <Advanced info={info} />}
    </Card>
  );
}

/** An on/off setting, said in words beside it. */
function Switch({ on, onChange, label, hint }: { on: boolean; onChange: (on: boolean) => void; label: string; hint: string }) {
  return (
    <label className="flex items-center gap-3 text-sm cursor-pointer select-none mt-3">
      <span className={clsx("w-9 h-5 rounded-full relative transition-colors shrink-0", on ? "bg-accent-brand" : "bg-bg-border")}>
        <span className={clsx("absolute top-[3px] w-[14px] h-[14px] rounded-full bg-bg-surface shadow transition-all", on ? "left-[19px]" : "left-[3px]")} />
      </span>
      <input type="checkbox" className="sr-only" checked={on} onChange={(e) => onChange(e.target.checked)} />
      <span>
        <span className="block font-medium">{label} <span className="text-xs font-normal text-text-muted">({on ? "on" : "off"})</span></span>
        <span className="block text-xs text-text-muted">{hint}</span>
      </span>
    </label>
  );
}

function Advanced({ info }: { info: SystemInfo }) {
  const queryClient = useQueryClient();
  const [repo, setRepo] = useState(info.repo ?? "");
  const [branch, setBranch] = useState(info.branch ?? "main");
  const [token, setToken] = useState("");
  const [saving, setSaving] = useState(false);
  const save = async (body: Parameters<typeof aagam.updateSettings>[0], done: string) => {
    setSaving(true);
    try {
      queryClient.setQueryData(["system"], await aagam.updateSettings(body));
      setToken("");
      toast.success(done);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <div className="mt-3 grid sm:grid-cols-2 gap-3 text-sm pop-in">
      <label className="block">
        <span className="text-xs text-text-muted">Repository on GitHub (owner/name)</span>
        <input className="input w-full mt-0.5 font-mono text-[13px]" value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="owner/AAGAM" />
      </label>
      <label className="block">
        <span className="text-xs text-text-muted">Branch</span>
        <input className="input w-full mt-0.5 font-mono text-[13px]" value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="main" />
      </label>
      <label className="block sm:col-span-2">
        <span className="text-xs text-text-muted">Access key, for a private repository (a read-only GitHub token)</span>
        <input type="password" autoComplete="off" className="input w-full mt-0.5" value={token} onChange={(e) => setToken(e.target.value)}
          placeholder={info.has_token ? "A key is saved. Type a new one to replace it." : "Leave empty for a public repository"} />
        <span className="block text-[11px] text-text-muted mt-1">It is kept on this computer only, locked to your Windows account, and never shown again.</span>
      </label>
      <div className="sm:col-span-2 flex flex-wrap gap-2">
        <button className="btn btn-primary py-1" disabled={saving} onClick={() => save({ repo: repo.trim(), branch: branch.trim() || "main", ...(token.trim() ? { token: token.trim() } : {}) }, "Saved.")}>
          {saving && <Loader2 size={13} className="animate-spin" />} Save
        </button>
        {info.has_token && <button className="btn py-1" disabled={saving} onClick={() => save({ token: null }, "The access key is removed.")}>Remove the access key</button>}
      </div>
    </div>
  );
}

const LOOK = {
  ok: { icon: CheckCircle2, word: "Fine", cls: "text-accent-green" },
  warn: { icon: AlertTriangle, word: "Worth a look", cls: "text-accent-amber" },
  fail: { icon: XCircle, word: "Needs fixing", cls: "text-accent-red" },
} as const;

function Health() {
  const queryClient = useQueryClient();
  const { data, error, isFetching, refetch } = useQuery({ queryKey: ["system-health"], queryFn: aagam.health, retry: (n, e) => !missing(e) && n < 1 });
  const [task, setTask] = useState<{ action: string; id: string } | null>(null);
  const repair = async (action: string) => {
    try {
      const r = await aagam.repair(action);
      setTask({ action, id: r.task });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };
  const fails = data?.checks.filter((c) => c.status === "fail").length ?? 0;
  const warns = data?.checks.filter((c) => c.status === "warn").length ?? 0;
  return (
    <Card
      title="Health of this computer"
      icon={<HeartPulse size={16} />}
      actions={<button className="btn py-1" onClick={() => refetch()} disabled={isFetching}>{isFetching ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />} Check again</button>}
    >
      {error ? (
        <p className="text-sm text-text-muted">{missing(error) ? "This copy of AAGAM can't check itself from the window yet." : (error as Error).message}</p>
      ) : !data ? (
        <p className="text-sm text-text-muted flex items-center gap-2"><Loader2 size={13} className="animate-spin" /> Checking…</p>
      ) : (
        <>
          <p className="text-sm text-text-secondary mb-3">
            {fails ? `${fails} thing${fails === 1 ? "" : "s"} to fix before AAGAM works properly.` : warns ? `AAGAM is ready. ${warns} optional thing${warns === 1 ? "" : "s"} worth a look.` : "AAGAM is ready. Everything it needs is here."}
          </p>
          <ul className="divide-y divide-bg-border">
            {data.checks.map((c) => <CheckRow key={c.key} check={c} onRepair={repair} />)}
          </ul>
        </>
      )}
      {task && (
        <TaskLog
          title={ACTIONS[task.action] ?? "Repairing"}
          task={task.id}
          onClose={() => {
            setTask(null);
            refetch();
            queryClient.invalidateQueries({ queryKey: ["system"] });
            queryClient.invalidateQueries({ queryKey: ["ai-status"] });
          }}
        />
      )}
    </Card>
  );
}

function CheckRow({ check: c, onRepair }: { check: HealthCheck; onRepair: (action: string) => void }) {
  const look = LOOK[c.status] ?? LOOK.warn;
  const Icon = look.icon;
  return (
    <li className="py-2.5 flex items-start gap-3">
      <span className={clsx("inline-flex items-center gap-1 text-xs font-medium w-28 shrink-0 pt-0.5", look.cls)}><Icon size={14} /> {look.word}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{c.label}</p>
        <p className="text-xs text-text-muted break-words">{c.detail}</p>
        {c.status !== "ok" && c.fix && <p className="text-xs text-text-secondary mt-0.5">→ {c.fix}</p>}
      </div>
      {c.action && c.status !== "ok" && (
        <button className="btn py-1 text-xs shrink-0" onClick={() => onRepair(c.action!)}><Wrench size={12} /> {ACTIONS[c.action] ?? "Fix it"}</button>
      )}
    </li>
  );
}

/** What a repair is doing, line by line, until it is done. */
function TaskLog({ title, task, onClose }: { title: string; task: string; onClose: () => void }) {
  const [state, setState] = useState<SystemTask | null>(null);
  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      try {
        const s = await aagam.task(task);
        if (stopped) return;
        setState(s);
        if (s.status === "running") window.setTimeout(tick, 2_000);
      } catch {
        if (!stopped) window.setTimeout(tick, 3_000);
      }
    };
    tick();
    return () => {
      stopped = true;
    };
  }, [task]);
  const running = !state || state.status === "running";
  return (
    <Modal title={title} onClose={onClose} width="max-w-2xl" footer={<button className="btn btn-primary" onClick={onClose}>{running ? "Close (it carries on)" : "Done"}</button>}>
      <p className="text-sm mb-2 flex items-center gap-2">
        {running ? <><Loader2 size={14} className="animate-spin text-accent-brand" /> Working… this can take a few minutes.</>
          : state.status === "done" ? <><CheckCircle2 size={14} className="text-accent-green" /> Finished.</>
          : <><XCircle size={14} className="text-accent-red" /> It didn't finish. The lines below say why.</>}
      </p>
      <pre className="text-xs bg-bg-hover/60 rounded-lg p-3 max-h-[50vh] overflow-auto whitespace-pre-wrap font-mono">{state?.log.join("\n") || "…"}</pre>
    </Modal>
  );
}

function Care() {
  const [busy, setBusy] = useState<"backup" | "support" | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const run = async (kind: "backup" | "support") => {
    setBusy(kind);
    setSaved(null);
    try {
      if (kind === "support") {
        const report = await aagam.supportReport();
        setSaved(report.path);
        toast.success("The report is saved. You can send that file.");
        return;
      }
      const started = await aagam.backup();
      for (;;) {
        const job = await aagam.job(started.task);
        if (job.status === "done" && job.path) {
          setSaved(job.path);
          toast.success(`Saved ${job.files} files. AAGAM itself was not changed.`);
          return;
        }
        if (job.status === "failed") {
          toast.error(job.error || "The copy didn't finish.");
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  };
  return (
    <Card title="Backups and help" icon={<LifeBuoy size={16} />}>
      <p className="text-sm text-text-secondary leading-6">
        Back up my data copies your documents and records into Documents, in a folder called AAGAM backups. AAGAM can stay open. Save a report for help writes a small file on the Desktop: the health check and recent logs, with no documents and no update key in it.
      </p>
      <div className="flex flex-wrap gap-2 mt-3">
        <button className="btn btn-primary" disabled={busy !== null} onClick={() => run("backup")}>
          {busy === "backup" ? <Loader2 size={14} className="animate-spin" /> : <Archive size={14} />} Back up my data
        </button>
        <button className="btn" disabled={busy !== null} onClick={() => run("support")}>
          {busy === "support" ? <Loader2 size={14} className="animate-spin" /> : <LifeBuoy size={14} />} Save a report for help
        </button>
      </div>
      {saved && (
        <div className="mt-3">
          <p className="text-xs text-text-muted">Saved here</p>
          <p className="font-mono text-xs break-all mt-0.5">{saved}</p>
          <button className="btn py-1 mt-2" onClick={() => aagam.reveal(saved).catch((e: Error) => toast.error(e.message))}>
            <FolderOpen size={14} /> Show in File Explorer
          </button>
        </div>
      )}
    </Card>
  );
}

function Uninstall({ onStarted }: { onStarted: () => void }) {
  const confirm = useConfirm();
  const [removeData, setRemoveData] = useState(false);
  const [typed, setTyped] = useState("");
  const [working, setWorking] = useState(false);
  const go = async () => {
    const ok = await confirm({
      title: "Uninstall AAGAM from this computer?",
      body: removeData ? "AAGAM and ALL your data in it are removed. This can't be undone." : "The AAGAM program is removed. Your data folder stays, so installing AAGAM again brings everything back.",
      items: [
        "The AAGAM program and its shortcuts",
        "AAGAM's entry in Claude Desktop",
        removeData ? "Your data folder: documents, clients, notes and work" : "Kept: your data folder (documents, clients, notes and work)",
      ],
      action: "Uninstall AAGAM",
      danger: true,
    });
    if (!ok) return;
    setWorking(true);
    try {
      await aagam.uninstall(removeData, removeData ? typed.trim() : "");
      onStarted();
    } catch (e) {
      toast.error((e as Error).message);
      setWorking(false);
    }
  };
  return (
    <Card title="Uninstall" icon={<PackageX size={16} />}>
      <p className="text-sm text-text-secondary leading-6">
        Removes the AAGAM program, its shortcuts and its entry in Claude Desktop. Your data folder is kept unless you choose to remove it too. Local AI (Ollama) and Python stay; remove them from Windows Settings → Apps if you like.
      </p>
      <label className="flex items-start gap-2 text-sm mt-3">
        <input type="checkbox" className="mt-1" checked={removeData} onChange={(e) => { setRemoveData(e.target.checked); setTyped(""); }} />
        <span>Also delete my data: every document, client, note and piece of work. <span className="text-accent-red">This can't be undone.</span></span>
      </label>
      {removeData && (
        <label className="block text-sm mt-2 pop-in">
          <span className="text-xs text-text-muted">Type REMOVE to confirm</span>
          <input className="input w-48 mt-0.5 font-mono" value={typed} onChange={(e) => setTyped(e.target.value)} aria-label="Type REMOVE to confirm" />
        </label>
      )}
      <button className="btn mt-4 text-accent-red" onClick={go} disabled={working || (removeData && typed.trim() !== "REMOVE")}>
        {working ? <Loader2 size={14} className="animate-spin" /> : <PackageX size={14} />} Uninstall AAGAM
      </button>
    </Card>
  );
}

function Removed() {
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-bg-primary/95 backdrop-blur-sm fade-in" role="alertdialog" aria-label="AAGAM is being removed">
      <div className="card p-8 max-w-md text-center pop-in">
        <PackageX size={30} className="mx-auto text-text-muted mb-3" />
        <p className="display text-xl font-semibold">AAGAM is being removed</p>
        <p className="text-sm text-text-secondary mt-2 leading-6">It takes a few seconds. You can close this window. To use AAGAM again, run install.cmd.</p>
      </div>
    </div>
  );
}
