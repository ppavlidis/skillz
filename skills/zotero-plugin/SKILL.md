---
name: zotero-plugin
description: >
  Expert guide for building, debugging, and releasing Zotero 7–9 bootstrapped plugins.
  Use this skill whenever someone is creating a Zotero plugin, writing bootstrap.js or
  a plugin JS file, wiring up Zotero menu items, attaching event listeners in a Zotero
  window, hitting Zotero API methods (Attachments, Notifier, HTTP, Search, ProgressWindow),
  troubleshooting a silent failure in a Zotero extension, or releasing a Zotero plugin
  to GitHub with auto-update support. Even if they just say "Zotero plugin" or "Zotero
  extension" without further detail, use this skill.
---

# Zotero Plugin Development

Patterns distilled from building multiple production Zotero 7–9 plugins. Apply these from
the start — most of the hard-won lessons here prevent subtle silent failures that are very
difficult to debug after the fact.

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
      if (event === "add")    handleAdd(ids).catch(log);
      if (event === "modify") handleModify(ids).catch(log);
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

## Icons — use PNG, not SVG

SVG icons don't render reliably in the Zotero add-ons manager.
Use `content/icons/favicon.png` (96×96) and `content/icons/favicon-48.png` (48×48).
Include the `content/` directory in the XPI zip.

## Preference panes — avoid if possible

`Zotero.PreferencePanes.register()` is fragile and takes significant effort to get right.
For simple settings, prefer `Services.prompt.prompt()` from a menu command.

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
