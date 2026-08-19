---
name: scenequant-ship
description: Push SceneQuant / ScreenQuantDev and publish the addon zip autonomously. Use when the user says push, ship, update GitHub, update listings, release, ScreenQuant, SceneQuant, or /scenequant-ship. Never use a Cursor GitHub-connect card.
---

# SceneQuant ship

Public repo is `liminallyspaced/ScreenQuantDev`. Clone: `C:\Users\nicks\Desktop\ScreenQuantDev`. Account: `liminallyspaced` via `gh` / GitHub MCP. Private `scenequant` is a different tree — do not push it here.

## Do this. Do not ask.

1. Work in `C:\Users\nicks\Desktop\ScreenQuantDev` (or GitHub MCP against `liminallyspaced/ScreenQuantDev` `main`).
2. Confirm `gh auth status` shows **liminallyspaced** with `repo`. If not: `gh auth switch --user liminallyspaced`.
3. Commit and **push immediately**:

```powershell
cd C:\Users\nicks\Desktop\ScreenQuantDev
git add -A
git commit -m "<what changed>"
git push origin main
```

Or GitHub MCP `github__push_files` / `github__create_or_update_file` to `owner=liminallyspaced` `repo=ScreenQuantDev` `branch=main`.

4. A push to `main` already rebuilds `scenequant-<ver>.zip` and updates the GitHub Release from `scenequant/blender_manifest.toml`. To ship from this machine instead:

```powershell
pwsh -NoProfile -File tools/ship.ps1
```

## Forbidden

- Cursor “Connect GitHub” cards
- Asking Nick to paste a PAT
- Creating another repo
- Leaving Gumroad / itch as drafts (those URLs are live; replace the file, keep published)

Live URLs and proof numbers: `listings.json` in the public repo.
