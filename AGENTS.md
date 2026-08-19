# SceneQuant — operating notes for agents

Read this before creating repos, sending “Connect GitHub” cards, or touching store listings.

## Canonical map

| What | Where |
|---|---|
| **Public product repo** | `https://github.com/liminallyspaced/ScreenQuantDev` |
| Local clone of that repo | `C:\Users\nicks\Desktop\ScreenQuantDev` |
| GitHub account to use | `liminallyspaced` (`gh` is already logged in: `repo` + `workflow`) |
| Other GitHub account | `nsiegelwebpro` — do **not** use it for this product |
| Private source (VRAM / “Make It Fit” track) | `https://github.com/liminallyspaced/scenequant` (private; 404 if logged out) |
| Local private clone | `C:\Users\nicks\Desktop\SceneQuant` — **not** the public product |
| Speed-track working copy (no git) | `C:\Users\nicks\Downloads\scenequant-bench\addon` |

The public product button is **Make it Fast**. The private `scenequant` tree’s **Make It Fit** button is a different lineage. Do not mix them, and do not create a third repo.

## Live listings — same URLs forever

Update the file on these pages. Do not create new products.

| Place | URL | Status |
|---|---|---|
| GitHub Releases | https://github.com/liminallyspaced/ScreenQuantDev/releases | live |
| itch.io | https://liminalvisual.itch.io/scenequant | live |
| Gumroad | https://8139959199815.gumroad.com/l/exyxdi | live ($0+) |
| Superhive | — | buyer account only; no creator shop |
| extensions.blender.org | — | not submitted; needs Blender ID |

Machine-readable copy: [`listings.json`](listings.json).

## How to push (this is the whole point)

```powershell
cd C:\Users\nicks\Desktop\ScreenQuantDev
gh auth status          # must be liminallyspaced, scopes repo + workflow
git add -A
git commit -m "…"
git push origin main
pwsh -NoProfile -File tools/ship.ps1    # zip + GitHub Release from blender_manifest.toml
```

- Use **`gh` / `git push`**. The token on this machine already works.
- **Never** send a Cursor “Connect GitHub” card. That is Cursor Integrations, not GitHub, and it cannot see this repo.
- **Never** ask Nick to paste a PAT in chat. If `git push` 403s, the account is wrong (`gh auth switch --user liminallyspaced`) or the token lacks `repo`.
- **Never** create `ScreenQuantDev2`, `scenequant-public`, etc.
- A fine-grained PAT without **Contents: Read and write** on `ScreenQuantDev` will 403. Don’t use one. Use `gh`.

Tagging `v*` also runs `.github/workflows/release.yml`, which attaches `scenequant-<ver>.zip`. Prefer `tools/ship.ps1` so the zip exists even if Actions is slow.

## Numbers you may print

Only these, and only as measured pairs — never “up to 70%”, never “every scene”:

- Classroom (Seux), Blender 4.5.5 LTS, 1920×1080, 300 spp: **2:43 → 1:35 (41%)**, MAE 5.6/255
- loft.blend, Blender 4.5.5 LTS, 1080×1350, 512 spp: **5:37 → 2:41 (52%)**, MAE 7.0/255
- loft.blend, Blender 5.1.2, same file/machine: **5:50 → 2:12 (62%)**, MAE 7.0/255

Machine: RTX 2080 Super Max-Q 8 GB · i7-10875H · 16 GB · Windows 11 · Cycles OptiX · factory-startup · persistent data off. loft timed at 100% (native 250%).

Proof plates: `docs/proof/loft-pair.jpg`, `classroom-pair.jpg`, `loft-51-pair.jpg`.

## Store updates

Listings are **live**, not drafts. After a release, replace the zip on the same Gumroad and itch URLs and leave them published. Superhive and Extensions stay untouched until a creator shop / Blender ID exists.

itch zip uploads need the `liminalvisual` account email verified (already done). `butler` is not installed; use the signed-in browser or install butler later.

## Product facts

- Addon id: `scenequant`
- Zip layout: `scenequant/blender_manifest.toml` at `scenequant/…` inside the zip
- Install the Release asset, never GitHub “Source code”
- License: GPL-3.0-or-later
- Price: $0
