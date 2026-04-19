---
name: zotero-plugin
description: >
  Expert guide for building, debugging, and releasing Zotero 7–9 plugins. Covers both
  the classic bootstrapped stack (bootstrap.js + plain JS + manifest.json) and the
  TypeScript stack built on zotero-plugin-scaffold and zotero-plugin-toolkit. Use this
  skill whenever someone is creating a Zotero plugin or extension, writing bootstrap.js,
  hooks.ts, or a plugin JS/TS file, wiring up Zotero menu items, attaching event
  listeners in a Zotero window, hitting Zotero API methods (Attachments, Notifier, HTTP,
  Search, ProgressWindow, Prefs, PreferencePanes), configuring a preference pane,
  debugging a MutationObserver in a React-rendered Zotero UI area, troubleshooting a
  silent failure in a Zotero extension, setting up or building a zotero-plugin-scaffold
  project, or releasing a Zotero plugin to GitHub with auto-update support. Even if they
  just say "Zotero plugin" or "Zotero extension" without further detail, use this skill.
---

# Zotero Plugin Development

Patterns distilled from building multiple production Zotero 7–9 plugins. Apply these from
the start — most of the hard-won lessons here prevent subtle silent failures that are very
difficult to debug after the fact.

## Two stacks — pick one before you start

Zotero plugins come in two flavors. Most of this doc is about the **classic** stack; the
**toolkit** stack has its own section at the end.

- **Classic bootstrapped** — `bootstrap.js` + plain JS + `manifest.json` at the repo root.
  Zero build step. Good for small plugins and fast iteration.
- **Toolkit** — TypeScript on top of
  [`zotero-plugin-scaffold`](https://github.com/northword/zotero-plugin-scaffold) +
  [`zotero-plugin-toolkit`](https://github.com/windingwind/zotero-plugin-toolkit).
  Type-safe `getPref`/`setPref`, Fluent localization, dev server with hot reload,
  templated manifest. Good for larger plugins and when you want types.

**Detect before asking.** If the repo already has `src/hooks.ts` or a `package.json` with
`zotero-plugin-scaffold` → toolkit. If it has a root-level `bootstrap.js` + plain JS →
classic. Match the existing stack; don't migrate without being asked.

**Ask only when starting from an empty directory.** One question: "Classic bootstrapped
(plain JS, no build) or toolkit stack (TypeScript, build pipeline)?"

## Manifest (`manifest.json`) — critical fields

```json
{
  "manifest_version": 2,
  "applications": {
    "zotero": {
      "id": "plugin-name@example.com",
      "update_url": "https://raw.githubusercontent.com/<user>/<repo>/main/updates.json",
      "strict_min_version": "7.0.0",
      "strict_max_version": "9.*"
    }
  }
}
```

- `update_url` is **required** — Zotero silently ignores the plugin without it
- `strict_max_version: "9.*"` covers Zotero 7, 8, and 9 (Zotero 9 released 2026-04-10)
- Plugin ID must be email-format: `something@example.com`
- Zotero 9 DOM structure and bootstrap lifecycle are identical to Zotero 8

## `bootstrap.js` — standard lifecycle

```js
var MyPlugin;

function install() {}

async function startup({ id, version, rootURI }) {
  await Zotero.initializationPromise;
  await Zotero.unlockPromise;
  await Zotero.uiReadyPromise;
  Services.scriptloader.loadSubScript(rootURI + "myplugin.js");
  MyPlugin.init({ id, version, rootURI });
  MyPlugin.addToAllWindows();
}

function onMainWindowLoad({ window }) { MyPlugin.addToWindow(window); }
function onMainWindowUnload({ window }) { MyPlugin.removeFromWindow(window); }

function shutdown() {
  MyPlugin.removeFromAllWindows();
  MyPlugin.destroy();
  MyPlugin = undefined;
}

function uninstall() {}
```

Always await all three startup promises before touching the DB or injecting UI.
`initializationPromise` alone is not enough — the main window isn't ready yet.

## Per-window UI management pattern

Every plugin that injects UI needs a clean add/remove cycle per window.
Track added element IDs and event listeners so `removeFromWindow` can undo everything:

```js
addToWindow(window) {
  if (this._windows.has(window)) return;
  const data = { addedElementIDs: [], listeners: [] };
  this._windows.set(window, data);
  // inject elements → push IDs to data.addedElementIDs
  // add event listeners → push { el, type, fn } to data.listeners
},

removeFromWindow(window) {
  const data = this._windows.get(window);
  if (!data) return;
  for (const { el, type, fn } of data.listeners) el.removeEventListener(type, fn);
  for (const id of data.addedElementIDs) window.document.getElementById(id)?.remove();
  this._windows.delete(window);
},
```

## XUL elements

```js
const el = doc.createXULElement("menuitem"); // NOT doc.createElement
el.setAttribute("label", "My Item");
```

Common parents: `zotero-itemmenu` (item context menu), `menu_ToolsPopup` (Tools menu).

**Context menu vs Tools menu:** Item-level operations (require a selection) belong in the
**context menu only** — the user's hands are already in the item list, right-click is
natural there. The Tools menu is for global/library-wide actions that don't need a
selection. Zotero's own "Find Available PDF" is context-menu-only — follow that pattern.

## Notifications — always use `ProgressWindow`, never modal dialogs

```js
// Good: non-blocking, auto-closes, doesn't steal focus
const pw = new Zotero.ProgressWindow({ closeOnClick: true });
pw.changeHeadline("Done: 2 PDFs found");
pw.addDescription("Optional detail line");
pw.show();
pw.startCloseTimer(4000); // ← REQUIRED — omitting this leaves the window open forever

// Bad: steals focus, blocks the UI while open
Services.prompt.alert(window, "Title", "Message");
```

Always call `startCloseTimer`. Avoid `closeOnClick: false` unless you have a specific reason.

For quick OK-only messages where focus-steal is acceptable, `Zotero.alert(window, title, msg)`
is shorter than `Services.prompt.alert`. For multi-button choice dialogs, use `confirmEx`:

```js
const BTN_0 = Services.prompt.BUTTON_POS_0 * Services.prompt.BUTTON_TITLE_IS_STRING;
const BTN_1 = Services.prompt.BUTTON_POS_1 * Services.prompt.BUTTON_TITLE_IS_STRING;
const BTN_2 = Services.prompt.BUTTON_POS_2 * Services.prompt.BUTTON_TITLE_IS_STRING;
const choice = Services.prompt.confirmEx(
  window, "Title", "Message",
  BTN_0 + BTN_1 + BTN_2,
  "Keep", "Replace", "Cancel",
  null, null, {}
);
// choice: 0 = Keep, 1 = Replace, 2 = Cancel
```

## Timers — use plain `setTimeout`, not `Zotero.setTimeout`

`Zotero.setTimeout` does not exist. Calling it fails silently, leaving timers that never fire:

```js
// Correct
const id = setTimeout(fn, ms);
clearTimeout(id);

// Wrong — silent failure
Zotero.setTimeout(fn, ms);
```

## HTTP requests

```js
const xhr = await Zotero.HTTP.request("GET", url, {
  timeout: 20000,
  headers: { Accept: "application/pdf, text/html, */*" },
});
const ct = (xhr.getResponseHeader?.("Content-Type") || "").toLowerCase();
const resolvedUrl = xhr.responseURL || url; // follow redirects
```

For probing a URL: try HEAD first, fall back to GET if HEAD fails.

## File existence — don't trust the database

Stale DB records can reference files that no longer exist. Always verify:

```js
const path = att.getFilePath();
if (!path || !(await IOUtils.exists(path))) continue;
```

For PDFs, verify magic bytes rather than trusting content-type — `importFromURL` can save
a login-redirect HTML page with `application/pdf` content-type:

```js
const bytes = await IOUtils.read(path, { maxReadSize: 5 });
const isPdf = bytes[0] === 0x25 && bytes[1] === 0x50 &&
              bytes[2] === 0x44 && bytes[3] === 0x46; // %PDF-
```

## Notifier — watching item events

```js
this._notifierID = Zotero.Notifier.registerObserver(
  {
    notify(event, type, ids) {
      if (type !== "item") return;
      if (event === "add")    handleAdd(ids).catch(e => Zotero.debug("myplugin: " + e));
      if (event === "modify") handleModify(ids).catch(e => Zotero.debug("myplugin: " + e));
    }
  },
  ["item"],
  "my-observer-id"
);

// In destroy():
Zotero.Notifier.unregisterObserver(this._notifierID);
```

**Important:** When the Zotero Connector saves an item, it adds the item first, then
modifies it to fill in metadata (DOI, title, etc.). The DOI is often not set at `add`
time — watch both `add` and `modify` events if you need it.

**Always `.catch` async work inside `notify`.** An uncaught rejection inside the observer
can propagate into Zotero's core event loop. Swallow with `Zotero.debug`.

## Searching by DOI

```js
const s = new Zotero.Search();
s.libraryID = item.libraryID;
s.addCondition("DOI", "is", normalizedDoi);
const ids = await s.search();
```

Normalize first: `doi.trim().toLowerCase().replace(/^https?:\/\/doi\.org\//i, "")`.

## Reparenting attachments

```js
att.parentID = newParentId;
await att.saveTx();
// Delete the now-empty original parent:
await oldParentItem.eraseTx();
```

## MutationObserver in React-rendered areas

Zotero's tab bar and some panels are React-rendered. React re-renders strip injected
elements. Pattern: watch for removal → debounce → re-inject.

**Critical:** disconnect the observer *before* re-injecting and reconnect *after*. If
you don't, the removal of old chips during re-injection triggers the observer again →
infinite loop.

```js
const obs = new window.MutationObserver((mutations) => {
  const removed = mutations.some(m =>
    Array.from(m.removedNodes).some(n => n.classList?.contains?.("my-class"))
  );
  if (!removed) return;
  if (debounceTimer) window.clearTimeout(debounceTimer);
  debounceTimer = window.setTimeout(() => {
    obs.disconnect();
    reinject();
    obs.observe(target, { childList: true, subtree: true });
  }, 60);
});
obs.observe(target, { childList: true, subtree: true });
```

Store `debounceTimer` in a state object (not a closure variable) so it can be cancelled
if state is replaced during re-grouping.

## Injecting a stylesheet

Load CSS from `content/` as a `<link>` in the window's `documentElement`. Track the node
so `removeFromWindow` can drop it:

```js
const link = doc.createElementNS("http://www.w3.org/1999/xhtml", "link");
link.rel = "stylesheet";
link.href = rootURI + "content/style.css";
link.id = "myplugin-style";
doc.documentElement.appendChild(link);
data.addedElementIDs.push("myplugin-style");
```

Use Zotero's CSS variables for colors so the plugin looks right in both light and dark
mode — e.g. `var(--material-toolbar-icon)`, `var(--fill-quinary)`, `var(--color-accent)`.
Inspect the Zotero DOM to find the variable that matches nearby built-in UI; don't
hard-code hex colors.

Prefer toggling classes on elements (and styling them in the stylesheet) over setting
`style.*` in JS — CSS respects theme variables and is easier to override.

## Icons — use PNG, not SVG

SVG icons don't render reliably in the Zotero add-ons manager.
Use `content/icons/favicon.png` (96×96) and `content/icons/favicon-48.png` (48×48).
Include the `content/` directory in the XPI zip.

## Preference panes

Register an XHTML pref pane at startup. The pane is just plain XHTML under `content/`
with an inline `<script>` that wires up listeners on window `load`:

```js
// In your plugin's init() (classic bootstrapped):
Zotero.PreferencePanes.register({
  pluginID: id,
  src: rootURI + "content/preferences.xhtml",
  label: "My Plugin",
  image: rootURI + "content/icons/favicon-48.png",
});
```

```xhtml
<!-- content/preferences.xhtml -->
<vbox xmlns="http://www.mozilla.org/keymaster/gatekeeper/there.is.only.xul">
  <checkbox id="my-pref-enabled" label="Enable feature"
            preference="extensions.myplugin.enabled"/>
  <script><![CDATA[
    window.addEventListener("load", () => {
      const cb = document.getElementById("my-pref-enabled");
      cb.checked = Zotero.Prefs.get("extensions.myplugin.enabled", true);
      cb.addEventListener("command", () => {
        Zotero.Prefs.set("extensions.myplugin.enabled", cb.checked, true);
      });
    });
  ]]></script>
</vbox>
```

Read prefs with `Zotero.Prefs.get("extensions.myplugin.key", true)` — the trailing `true`
scopes to the `extensions.` branch. For structured state, JSON-serialize:

```js
Zotero.Prefs.set("extensions.myplugin.groups", JSON.stringify(groups), true);
const groups = JSON.parse(Zotero.Prefs.get("extensions.myplugin.groups", true) || "[]");
```

When persisting state that references items, use stable `itemID`s, not ephemeral tab IDs
or window-local handles — tabs get new IDs on restart.

For one-off prompts instead of a full pane, `Services.prompt.prompt(window, title, msg, out, …)`
is fine from a menu command.

## Build & release

```bash
# Build XPI (from project root)
zip -r plugin-name.xpi bootstrap.js manifest.json plugin.js content/ updates.json

# Tag and release
git tag vX.Y.Z && git push --tags
gh release create vX.Y.Z plugin-name.xpi --title "vX.Y.Z" --notes "..."
```

`updates.json` must contain an entry pointing to the GitHub release download URL —
Zotero checks this URL for auto-updates. Without it, installed plugins never update.

## Keep the README in sync with code changes

After any user-visible change to a plugin, check `README.md` and update it if needed.
The README is how users discover what the plugin does and how to use it — code changes
that don't touch it leave the docs silently wrong.

Review the README when the change adds, removes, or alters:

- A menu item, keyboard shortcut, or right-click entry (update the "Usage" / features list).
- A preference or pref pane option (update any settings docs or screenshots).
- Supported Zotero versions (`strict_min_version` / `strict_max_version` in manifest →
  also mention in the README's requirements).
- Installation steps, the XPI filename, or the GitHub release URL.
- Observable behavior a user could notice (new notifications, different defaults, etc.).

Pure internal refactors with no behavior change don't need a README update — but say so
when reporting the task as done, so the user knows you checked.

## Info panel DOM (for plugins that modify the item info pane)

- Rows: `div.meta-row` inside `div#info-table`
- Field name: `div.meta-label[fieldname]` attribute
- Value: `editable-text` — check `.value` prop first, then `[value]` attr
- Creator rows: `.creator-type-value` instead of `.meta-data`
- Section header: `collapsible-section > div.head > .twisty`
- No Shadow DOM — regular CSS from `doc.documentElement` applies
- Zotero renders only the first 5 creators; `div#more-creators-label` is the "N more…" expander

## Tab internals (for plugins that work with reader tabs)

- `Zotero_Tabs._tabs` — array of `{id, type, data: {itemID}, ...}`
- Tab types: `"reader"` (loaded), `"reader-unloaded"` (memory-saved, itemID still valid), `"note"` — filter for all three, not just `"reader"`
- `Zotero_Tabs.move(id, index)` — reorder tabs (0 = library tab)
- Tab bar is React-rendered (`#tab-bar-container`) — inject as siblings, not into the React tree

---

# Toolkit stack (`zotero-plugin-scaffold` + `zotero-plugin-toolkit`)

Everything above still applies conceptually — these are the same APIs, just wrapped.
This section covers what's *different* when using the TypeScript build pipeline.

## Project layout

```
src/
  index.ts          # entry; creates Addon singleton, defines globals
  addon.ts          # Addon class (data, hooks, api)
  hooks.ts          # onStartup / onMainWindowLoad / onShutdown / onNotify / onPrefsEvent
  modules/          # real feature code; one file per concern
  utils/
    prefs.ts        # typed getPref / setPref wrappers
    locale.ts       # getString(key) for Fluent lookups
    ztoolkit.ts     # createZToolkit() factory
addon/
  bootstrap.js      # classic bootstrap, generated — don't edit by hand
  manifest.json     # uses __addonID__, __addonName__ placeholders
  prefs.js          # default pref values with __prefsPrefix__ placeholders
  content/
    preferences.xhtml   # pref pane (Fluent-localized)
    icons/
  locale/en-US/*.ftl    # Fluent strings
package.json        # .config holds addonRef, addonID, addonName, prefsPrefix
tsconfig.json       # extends "zotero-types/entries/sandbox"
```

The `config` object in `package.json` drives template substitution — placeholders like
`__addonID__`, `__prefsPrefix__`, `__addonRef__` in `addon/` files are replaced at build
time. Never hardcode these strings; read them from `config` in TS code.

## Key commands

- `npm start` → `zotero-plugin serve` — dev Zotero with hot reload
- `npm run build` → `zotero-plugin build && tsc --noEmit` — builds the XPI into `.scaffold/build/`
- `npm run release` → `zotero-plugin release` — tags, builds, pushes GitHub release
- `npm run lint:fix` — prettier + eslint

## `hooks.ts` — the dispatch layer

Keep `hooks.ts` thin. It awaits the same three promises as classic bootstrap, then
delegates to `modules/`:

```ts
async function onStartup() {
  await Promise.all([
    Zotero.initializationPromise,
    Zotero.unlockPromise,
    Zotero.uiReadyPromise,
  ]);
  initLocale();
  await onMainWindowLoad({ window: Zotero.getMainWindow() });
}

async function onMainWindowLoad({ window: win }: { window: _ZoteroTypes.MainWindow }) {
  addon.data.ztoolkit = createZToolkit();
  win.MozXULElement.insertFTLIfNeeded(`${addon.data.config.addonRef}-mainWindow.ftl`);
  // ...register UI via ztoolkit...
}

function onPrefsEvent(type: string, data: { [key: string]: any }) {
  if (type === "load") registerPreferenceListeners(data.window);
}

export default { onStartup, onMainWindowLoad, onShutdown, onNotify, onPrefsEvent };
```

## Typed prefs (`utils/prefs.ts`)

```ts
import { config } from "../../package.json";

type PluginPrefsMap = _ZoteroTypes.Prefs["PluginPrefsMap"];
const PREFS_PREFIX = config.prefsPrefix;

export function getPref<K extends keyof PluginPrefsMap>(key: K) {
  return Zotero.Prefs.get(`${PREFS_PREFIX}.${key}`, true) as PluginPrefsMap[K];
}

export function setPref<K extends keyof PluginPrefsMap>(key: K, value: PluginPrefsMap[K]) {
  return Zotero.Prefs.set(`${PREFS_PREFIX}.${key}`, value, true);
}
```

Declare `PluginPrefsMap` in a module augmentation so keys are type-checked:

```ts
// src/types/prefs.d.ts
declare namespace _ZoteroTypes {
  interface Prefs {
    PluginPrefsMap: {
      "enabled": boolean;
      "scale": "auto" | "page-width" | "page-fit";
    };
  }
}
```

## `prefs.js` (the default-values file)

Must exist in `addon/` even if you have no UI — Zotero reads it to seed defaults:

```js
/* eslint-disable no-undef */
pref("__prefsPrefix__.enabled", true);
pref("__prefsPrefix__.scale", "auto");
```

`__prefsPrefix__` is substituted at build from `package.json` `config.prefsPrefix`.

## Preference pane (Fluent-localized)

```xhtml
<!-- addon/content/preferences.xhtml -->
<vbox xmlns="http://www.mozilla.org/keymaster/gatekeeper/there.is.only.xul">
  <checkbox id="__addonRef__-enabled" data-l10n-id="pref-enabled"/>
</vbox>
```

Listeners go in `src/modules/preferenceScript.ts`, called from `onPrefsEvent("load", window)`:

```ts
export function registerPreferenceListeners(win: Window) {
  const cb = win.document.getElementById(`${config.addonRef}-enabled`) as HTMLInputElement;
  cb.checked = getPref("enabled");
  cb.addEventListener("command", () => setPref("enabled", cb.checked));
}
```

## Fluent strings

```
# addon/locale/en-US/preferences.ftl
pref-enabled = Enable the feature
```

Load in `onMainWindowLoad` with `win.MozXULElement.insertFTLIfNeeded(...)`. Look up from
TS code via `getString("pref-enabled")` (from `utils/locale.ts`).

## `ztoolkit` — the toolkit wrapper

`createZToolkit()` returns an object with helpers for registering menus, shortcuts,
notifiers, dialogs, prompts, progress windows, etc. — with automatic cleanup tracking.
Prefer `ztoolkit.UI.createElement` and `ztoolkit.Menu.register` over raw `createXULElement`
in toolkit plugins; cleanup is handled on shutdown.

When you need a raw API not wrapped by ztoolkit, fall back to `Zotero.*` directly — the
toolkit is a convenience, not a wall.

## When to pick toolkit over classic

- Plugin has more than ~500 LOC of TS-worthy logic.
- You want a real pref pane with localization.
- You want types against `zotero-types` (catches API-surface bugs at compile time).
- You're forking an upstream plugin already on this stack.

Stick with classic when the plugin is small (one feature, one menu item) and you value
zero build step.
