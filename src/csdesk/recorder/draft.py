"""Turn a recording into a readable flow (flow.md) and a draft recipe (recipe_draft.py).

The draft is a starting point to review, not a finished recipe: every field the
recorder couldn't tie to the company file, or couldn't find by a dependable
label, is marked TODO.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .values import SENSITIVE_KEYS, SENSITIVE_SHAPES

# Label sources Playwright's get_by_label also uses, so a recipe can find the field by them.
DEPENDABLE_LABELS = frozenset({"label", "aria-labelledby", "aria-label"})
VERDICTS = {
    "allowed": "CS Desk may press it",
    "hers": "hers; CS Desk never presses it",
    "not_listed": "not on CS Desk's list; it won't press it unless that list is changed after review",
    "unnamed": "no readable name; CS Desk won't press it",
}


@dataclass
class Step:
    number: int
    reason: str = ""
    page_url: str = ""
    heading: str = ""
    title: str = ""
    fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    changes: list[dict[str, Any]] = field(default_factory=list)
    clicks: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)


def load_events(folder: Path) -> list[dict[str, Any]]:
    path = folder / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a line cut short when the recorder was killed
    return events


def group_steps(events: list[dict[str, Any]]) -> list[Step]:
    steps: dict[int, Step] = {}
    for event in events:
        number = event.get("step", 0)
        if number == 0 and event["type"] not in ("started",):
            number = 1
        step = steps.setdefault(number, Step(number))
        kind = event["type"]
        if kind == "step":
            step.reason = event.get("reason", "")
        elif kind == "navigate":
            step.page_url = event["url"]
        elif kind == "snapshot":
            if not step.page_url:
                step.page_url = event.get("page_url", "")
            if not event.get("in_frame"):
                step.heading = event.get("heading") or step.heading
                step.title = event.get("title") or step.title
            for item in event.get("fields", []):
                step.fields[f"{event.get('frame_url')}|{item.get('selector')}"] = {**item, "in_frame": event.get("in_frame")}
        elif kind == "change":
            step.changes.append(event)
            step.timeline.append(event)
            step.page_url = step.page_url or event.get("page_url", "")
        elif kind == "click":
            step.clicks.append(event)
            step.timeline.append(event)
        elif kind in ("dialog", "request", "note", "tab_closed"):
            step.timeline.append(event)
        elif kind == "screenshot":
            step.screenshots.append(event["file"])
    for step in steps.values():
        # The form's page is the one she typed into, whatever other tabs reported.
        typed_on = [c.get("page_url") for c in step.changes if c.get("page_url")]
        if typed_on:
            step.page_url = max(set(typed_on), key=typed_on.count)
    return [steps[n] for n in sorted(steps) if n > 0]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "field"


def _key_of(match: str) -> str:
    return match.split(" (", 1)[0]


def filled_fields(step: Step) -> list[dict[str, Any]]:
    """One draft field per control she changed in this step, in the order she first changed it."""
    entries: dict[str, dict[str, Any]] = {}
    labels = [f.get("label", "").casefold() for f in step.fields.values() if f.get("type") != "radio"]
    for change in step.changes:
        f, v = change["field"], change["value"]
        if v.get("kind") == "secret" or f.get("secret"):
            continue
        if f.get("type") == "radio":
            group = f.get("group_selector") or f.get("name") or f.get("selector")
            ident = f"radio|{group}"
        else:
            ident = f"{change.get('frame_url')}|{f.get('selector')}"
        entry = entries.setdefault(ident, {"field": f, "value": v, "in_frame": change.get("in_frame")})
        entry["field"], entry["value"] = f, v  # the last change wins; the position stays where she started

    drafts = []
    for entry in entries.values():
        f, v = entry["field"], entry["value"]
        todo: list[str] = []
        matches = v.get("matches") or []
        if matches:
            key = _key_of(matches[0])
            if len(matches) > 1:
                todo.append(f"also matched {', '.join(matches[1:])}; check which one the form wants")
        else:
            named = f.get("group_label") if f.get("type") == "radio" else None
            key = f"extra.{_slug(named or f.get('label') or f.get('name') or f.get('id') or f.get('selector') or 'field')}"
            todo.append("no match in the company file: supply it as an extra value or add it to the company file")

        kind = {"select": "select", "checkbox": "checkbox", "radio": "radio", "file": "file", "date": "date"}.get(
            f.get("type", ""), "date" if v.get("date_format") else "text"
        )
        if f.get("tag") == "select":
            kind = "select"
        label, selector = f.get("label", ""), None
        if kind == "radio":
            label = f.get("group_label") or f.get("name") or "radio group"
            selector = f.get("group_selector")
            if not selector:
                todo.append("radio group has no name to find it by; write a selector")
            if not f.get("group_label"):
                todo.append("radio group has no question text; name it from the screenshot")
        elif f.get("label_source") not in DEPENDABLE_LABELS or not label or labels.count(label.casefold()) != 1:
            selector = f.get("selector")
            why = "no label" if not label else f"label comes from {f.get('label_source')}" if f.get("label_source") not in DEPENDABLE_LABELS else "label isn't unique on the page"
            todo.append(f"{why}; found by CSS selector, which breaks more easily")
            label = label or f.get("name") or f.get("id") or "unlabelled field"
        if entry["in_frame"]:
            todo.append("this field is inside a frame, which the form filler can't reach yet")
        shape = v.get("shape") or v.get("option") or ("ticked" if v.get("checked") else v.get("kind", ""))
        sensitive = key.split(".")[-1] in SENSITIVE_KEYS or v.get("shape") in SENSITIVE_SHAPES
        drafts.append(
            {
                "key": key,
                "label": label,
                "kind": kind,
                "selector": selector,
                "required": bool(f.get("required")),
                "sensitive": sensitive,
                "date_format": v.get("date_format") if kind == "date" else None,
                "entered": shape if kind != "file" else f"file ({len(v.get('files', []))})",
                "matched": [m for m in matches],
                "todo": todo,
            }
        )
    return drafts


def _portal_filled(step: Step) -> list[str]:
    changed = {c["field"].get("selector") for c in step.changes}
    found = []
    for f in step.fields.values():
        if f.get("has_value") and f.get("selector") not in changed and f.get("type") not in ("radio", "checkbox", "file"):
            found.append(f"{f.get('label') or f.get('name') or f.get('selector')}{' (read-only)' if f.get('readonly') else ''}")
    return found


def _left_empty(step: Step) -> list[str]:
    changed = {c["field"].get("selector") for c in step.changes}
    return [
        f.get("label") or f.get("name") or f.get("selector")
        for f in step.fields.values()
        if f.get("required") and not f.get("has_value") and f.get("selector") not in changed
    ]


def _var(form: str, number: int, many: bool) -> str:
    base = re.sub(r"[^A-Z0-9]+", "_", form.upper()).strip("_") or "FORM"
    return f"{base}_STEP_{number}" if many else base


def recipe_source(meta: dict[str, Any], steps: list[tuple[Step, list[dict[str, Any]]]]) -> str:
    form = meta["form"]
    many = len(steps) > 1
    out = [
        f'"""Draft recipe for {form}, recorded {meta.get("started_at", "")[:16].replace("T", " ")} (recording {meta["id"]}).',
        "",
        "Written from her own filling. Review every TODO, check the labels against the live form,",
        "then copy the recipe into src/csdesk/forms/registry.py. None of the values she typed are in this file:",
        "each key says where the form filler will take the value from.",
    ]
    if many:
        out += ["", "The form has several steps. fill_form fills one step per call for now, so each step is its own recipe."]
    out += ['"""', "", "from csdesk.forms.recipe import Field, Recipe", ""]
    for step, drafts in steps:
        clicks = ", ".join(f'"{c.get("name") or "?"}" ({c.get("guard")})' for c in step.clicks) or "none"
        save = next((c.get("name") for c in reversed(step.clicks) if c.get("guard") == "allowed" and re.search(r"save", c.get("name") or "", re.I)), None)
        marker = step.heading or step.title
        url_part = re.sub(r"^https?://[^/]+", "", step.page_url) or step.page_url
        out += ["", f"# Step {step.number}: {marker or 'no heading'}", f"# Buttons she pressed here: {clicks}"]
        out.append(f"{_var(form, step.number, many)} = Recipe(")
        out.append(f"    code={(f'{form}/step{step.number}' if many else form)!r},")
        out.append(f"    title={f'{form}, step {step.number} (recorded)' if many else f'{form} (recorded)'!r},")
        out.append(f"    url_contains={url_part!r},{'  # TODO: path is empty; use part of the address that only this form has' if not url_part.strip('/') else ''}")
        out.append(f"    page_marker={marker!r},{'  # TODO: no heading on the page; pick text that only this form shows' if not marker else ''}")
        out.append("    fields=(")
        for d in drafts:
            args = [repr(d["key"]), repr(d["label"])]
            if d["kind"] != "text":
                args.append(f"kind={d['kind']!r}")
            if d["selector"]:
                args.append(f"selector={d['selector']!r}")
            if not d["required"]:
                args.append("required=False")
            if d["sensitive"]:
                args.append("sensitive=True")
            if d["date_format"] and d["date_format"] != "%d/%m/%Y":
                args.append(f"date_format={d['date_format']!r}")
            note = "TODO: " + "; ".join(d["todo"]) if d["todo"] else f"matched {d['matched'][0]}" if d["matched"] else ""
            out.append(f"        Field({', '.join(args)}),{'  # ' + note if note else ''}")
        out.append("    ),")
        out.append(f"    save_button={save!r},")
        out.append(f"    recorded_on={meta.get('started_at', '')[:10]!r},")
        out.append(")")
    return "\n".join(out) + "\n"


def _time(event: dict[str, Any]) -> str:
    return event.get("t", "")[11:19]


def _timeline_lines(step: Step) -> list[str]:
    lines, last = [], None
    for event in step.timeline:
        kind = event["type"]
        if kind == "change":
            f = event["field"]
            name = f.get("group_label") if f.get("type") == "radio" else f.get("label") or f.get("name") or f.get("selector")
            secret = event["value"].get("kind") == "secret" or f.get("secret")
            line = "typed into a password, OTP or captcha field (not recorded)" if secret else f"changed **{name}**"
        elif kind == "click":
            line = f"pressed **{event.get('name') or '?'}** ({VERDICTS.get(event.get('guard'), event.get('guard'))})"
        elif kind == "dialog":
            line = f"dialog ({event.get('dialog_type')}): \"{event.get('message')}\""
        elif kind == "request":
            status = "failed" if event.get("failed") else event.get("status")
            keys = f" ?{'&'.join(event.get('query_keys') or [])}" if event.get("query_keys") else ""
            line = f"`{event.get('method')} {event.get('url')}{keys}` → {status} ({event.get('resource_type')}, {event.get('ms')} ms)"
        elif kind == "note":
            line = f"_{event.get('text')}_"
        else:
            line = "tab closed"
        if line == last:
            continue
        last = line
        lines.append(f"- {_time(event)} {line}")
    return lines


def flow_markdown(meta: dict[str, Any], steps: list[Step], drafts: dict[int, list[dict[str, Any]]], events: list[dict[str, Any]], review: list[str]) -> str:
    started = meta.get("started_at", "")
    stopped = next((e for e in reversed(events) if e["type"] == "stopped"), None)
    filled = sum(len(d) for d in drafts.values())
    matched = sum(1 for d in drafts.values() for item in d if item["matched"])
    who = [meta.get("company_name"), meta.get("party_name")]
    out = [
        f"# {meta['form']}: recorded flow",
        "",
        f"Recorded {started[:16].replace('T', ' ')}"
        + (f" to {stopped['t'][11:16]}" if stopped else "")
        + (f" · {' · '.join(w for w in who if w)}" if any(who) else "")
        + f" · {len(steps)} step(s) · {filled} field(s) filled, {matched} matched to the company file",
        "",
        "What she typed isn't stored. Each value is described by its shape and by the company-file field it matched.",
        f"Draft recipe: `recipe_draft.py`. Stopped: {stopped['reason'] if stopped else 'not recorded (the recorder ended early)'}.",
    ]
    for step in steps:
        out += ["", f"## Step {step.number}: {step.heading or step.title or 'no heading'}", ""]
        out.append(f"Page: {step.page_url or 'unknown'}" + (f" · why a new step: {step.reason}" if step.reason else ""))
        if step.screenshots:
            out.append("Screenshots: " + ", ".join(f"[{Path(s).name}]({s})" for s in step.screenshots))
        items = drafts.get(step.number, [])
        if items:
            out += ["", "| # | Field | Type | She entered | Company file |", "|---|---|---|---|---|"]
            for index, d in enumerate(items, 1):
                source = ", ".join(d["matched"]) or "—"
                out.append(f"| {index} | {d['label']} | {d['kind']} | {d['entered']} | {source} |")
        portal = _portal_filled(step)
        if portal:
            out += ["", "Already filled when she got there (by the portal, or left as found): " + "; ".join(portal) + "."]
        empty = _left_empty(step)
        if empty:
            out += ["", "Marked required but left empty: " + "; ".join(empty) + "."]
        timeline = _timeline_lines(step)
        if timeline:
            out += ["", "What happened, in order:", *timeline]
    if review:
        out += ["", "## To review before using the recipe", *[f"- {item}" for item in review]]
    return "\n".join(out) + "\n"


def build(folder: Path) -> dict[str, Any]:
    """Write flow.md and recipe_draft.py for a recording folder; return a summary."""
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    events = load_events(folder)
    steps = group_steps(events)
    drafts = {step.number: filled_fields(step) for step in steps}
    with_fields = [(step, drafts[step.number]) for step in steps if drafts[step.number]]

    review: list[str] = []
    for step, items in with_fields:
        for d in items:
            for todo in d["todo"]:
                review.append(f"Step {step.number}, {d['label']}: {todo}.")
        if not (step.heading or step.title):
            review.append(f"Step {step.number}: no heading to check the page by.")
    blocked = sorted({c.get("name") for s in steps for c in s.clicks if c.get("guard") == "not_listed" and c.get("name")})
    if blocked:
        review.append(
            "She pressed buttons CS Desk isn't allowed to press: "
            + ", ".join(f'"{b}"' for b in blocked)
            + ". If a recipe needs one, add it to the guard's list only after checking it can't submit, sign or pay."
        )
    if len(with_fields) > 1:
        review.append("This form has several steps; fill_form fills one step per call until multi-step replay is built.")

    (folder / "flow.md").write_text(flow_markdown(meta, steps, drafts, events, review), encoding="utf-8")
    if with_fields:
        (folder / "recipe_draft.py").write_text(recipe_source(meta, with_fields), encoding="utf-8")
    stopped = next((e for e in reversed(events) if e["type"] == "stopped"), None)
    return {
        "recording": meta["id"],
        "form": meta["form"],
        "folder": str(folder),
        "steps": len(steps),
        "steps_with_fields": len(with_fields),
        "fields_filled": sum(len(items) for _, items in with_fields),
        "matched": sum(1 for _, items in with_fields for d in items if d["matched"]),
        "to_review": review,
        "flow": str(folder / "flow.md"),
        "recipe_draft": str(folder / "recipe_draft.py") if with_fields else None,
        "screenshots": sum(len(s.screenshots) for s in steps),
        "events": len(events),
        "stopped": stopped["reason"] if stopped else None,
        "built_at": datetime.now().isoformat(timespec="seconds"),
    }
