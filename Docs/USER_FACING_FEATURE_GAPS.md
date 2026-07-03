# User-Facing Feature Differences: Reference vs Current Editor

Scope: compare the current `nba2k_editor` against the 2KVL reference folder. This file only lists user-facing capabilities that the reference exposes and the current editor does not expose, or only partially exposes. It does not say the current roster screen is broken.

## Present in current editor

These are not gaps:

- Live memory editor for Players, Draft Class, Teams, Staff, Stadiums, Jerseys, Shoes, NBA History, NBA Records.
- Generic grouped field editor with read/write/reset behavior.
- Player team filter/search, multi-select/batch editing, roster snapshot export/apply, Stat ID bulk reset.
- Team summary save, Team slot ownership, Team Records/NBA Records/History edit surfaces.
- Player Generator source/load/preview/pool SQL/import workflows.
- Franchise command center for live snapshot import, LLM prompt/result handling, and applying trade/signing/draft/roster actions through existing editor write seams.

## Missing or materially weaker user-facing features

| Priority | Reference feature | Reference user-facing behavior | Current editor state | Gap / required feature lane | Evidence |
|---:|---|---|---|---|---|
| 1 | Support & Proof | A visible support/proof page, capability matrix, current folder/runtime/mod-manager status, and small support ZIP export. | No equivalent page or ZIP/report export in `nba2k_editor`. | Add a Support/Proof screen that exports editor status, target, loaded domains, offset config, recent operation logs, and small reproducible proof files. | Ref: `docs/VENUELAB_PORTABLE_BUILD.md:217-230`, `47-68`; ours: no matching UI in `ui/qt_app.py`. |
| 1 | Archive Browser | Browse live install/archive tree with Folder Tree, Results, Inspector, preview/export/why-not badges, raw export, decoded SCNE text export. | No archive browser or game-install file explorer. | New archive-browser lane; likely outside current live-memory editor domain. | Ref: `docs/VENUELAB_PORTABLE_BUILD.md:149-168`; CLI `tools/venue_viewer_app.py:1179-1190`. |
| 1 | 3D venue/IFF/SCNE viewer | Open IFF/SCNE/OBJ/folders, toggle meshes, fit/orbit/pan/zoom, texture load, side-by-side preview, OBJ export. | No 3D viewer or venue preview. | Add viewer capability only if desired as separate feature lane; do not replace roster UI. | Ref: `docs/VENUE_VIEWER_APP.md:34-52`, `272-340`; `tools/venue_viewer_app.py:486-502`. |
| 1 | Mod Manager | Package cards, enabled/disabled/pending states, conflict winner summary, package details, move/enable controls, export active setup. | No mod package library or package route management. | Add Mod Manager package workflow if we want 2KVL-like mod install/session management. | Ref: `docs/VENUELAB_PORTABLE_BUILD.md:74-97`. |
| 1 | Hook Tools / live routing | Manual Connect to Game, Start/Stop Live Routing, Export Runtime Report, runtime status, route evidence. | Current editor attaches to process for memory reads/writes only; no runtime DLL companion, route observe, redirect profile, or runtime report UI. | Separate runtime companion lane; keep hard offline/EAC-off boundary if implemented. | Ref: `docs/VENUELAB_PORTABLE_BUILD.md:103-122`; `tools/VenueLabRuntimeHook/README.md:87-139`, `312-348`. |
| 2 | Runtime support report integration | Support reports include runtime route hits/misses, last requested route, Mod Manager conflict losers, hashes, skipped files. | Current editor has operation status but not structured exportable evidence bundle. | Extend Support/Proof with operation evidence and optional runtime/mod-manager sections if those features exist. | Ref: `docs/VENUELAB_PORTABLE_BUILD.md:47-61`. |
| 2 | Arena Builder | Export Blender carrier template, inspect `.vlabpack`, write review JSON/Markdown, render read-only build preview. | No arena authoring/build package workflow. | New Venue/Arena Tools lane; not a roster-editor fix. | Ref: `docs/VENUE_VIEWER_APP.md:342-451`; `tools/arena_builder.py`. |
| 2 | Arena Scene Workbench | Analyze ZIP IFF, packed VCZ/Oodle IFF, raw SCNE/RDAT; show scene fields/camera clamp data; write report. | No scene workbench. | Add diagnostic scene tool only if venue tooling is in scope. | Ref: `docs/VENUELAB_PORTABLE_BUILD.md:306-319`; `tools/arena_scene_workbench.py`. |
| 2 | Player field-set copy/paste | Copy selected player field set JSON, copy spreadsheet row, paste field set into inputs before guarded Set All write. | Current editor has roster snapshot export/apply and generator import, but not a small UI copy/paste field-set workflow for selected player inputs. | Add selected-player field-set copy/paste to existing player editor, reusing grouped field rows. | Ref: `docs/VENUELAB_PORTABLE_BUILD.md:251-263`; ours: player editor save/reset paths `ui/qt_app.py`. |
| 2 | In-app route catalogs | Shoe/portrait/uniform/arena-floor manifests and route helpers surface usable app lists and route proof. | Current editor has schema dropdowns and shoe relation but not route manifest/catalog browsers. | Add catalog panels only where they support existing Shoes/Jerseys/Stadiums/Players fields. | Ref: `tools/roster_shoe_catalog.py`, `tools/roster_portrait_cache.py`, `tools/extract_uniform_route_manifest.py`, `tools/extract_arena_floor_manifest.py`. |
| 2 | Legacy roster file tooling | 2K14 IFF/ROS read/write/roundtrip, arena swap, legacy profiles. | Current editor is live-memory/schema-based; no legacy file editor. | Separate legacy-file support lane. | Ref: `tools/roster_legacy_2k14.py`, `tools/roster_legacy_2k14_write.py`, `tools/roster_legacy_2k14_roundtrip.py`. |
| 2 | 2K25 audit/probe suite | Dedicated 2K25 field/write audit tools and fast live catalog probes. | Current offsets support target labels through 2K25, but app workflow is primarily current split-schema editor; no exposed 2K25 audit/proof UI. | Add target/version proof pages if 2K25 is a supported user-facing claim. | Ref: `tools/audit_nba2k25_roster_field_writes.py`, `tools/roster_live_memory_probe.py:11839-11856`. |
| 3 | Viewer preview accuracy/status | Preview Accuracy labels, staged status `Decoding mesh` / `Loading textures` / `Building scene` / `Preview loaded`. | Not applicable because no viewer; current operations show progress popup/status. | If a viewer is added, carry status-stage pattern. | Ref: `docs/VENUELAB_PORTABLE_BUILD.md:124-143`. |
| 3 | Side-by-side comparison | Side By Side opens two previews in one app window. | No visual compare surface. | Only needed with viewer lane. | Ref: `docs/VENUE_VIEWER_APP.md:45-46`, `tools/venue_viewer_app.py:495`. |
| 3 | Package/library empty-state actions | Create Package Folder, Choose Library, Use NBA 2K26 Mod Library. | No package library concept. | Belongs to Mod Manager lane. | Ref: `docs/VENUELAB_PORTABLE_BUILD.md:82-85`. |
| 3 | Release/portable publish tooling | Published portable folder, smoke tests, release hashes, ZIP gate docs. | Current repo has app spec/entrypoints, but no comparable user-facing release/publish proof page. | Add only if distributing the editor as a product build. | Ref: `docs/VENUELAB_PORTABLE_BUILD.md:3-45`, `544-647`. |

## Not a missing-feature claim

- Do not rewrite the current roster/editor screen just because 2KVL uses WebView2/HTML for venue/mod workflows. Current editor is a PyQt6 live-memory editor and its roster screen is a separate working surface.
- Do not add WebView2/Three.js to the current editor unless the requested feature is venue/archive visual tooling.
- Do not merge 2KVL runtime redirect behavior into normal memory editing. Hook Tools is a separate offline runtime-companion lane with hard boundaries.

## Practical build order if we implement gaps later

1. Support & Proof for the existing editor first: lowest risk, immediately useful, no architecture replacement.
2. Player field-set copy/paste inside the existing Player editor: small user-facing improvement on an existing surface.
3. Route/catalog panels for existing Shoes/Jerseys/Stadiums fields: only where it helps current editor writes.
4. Archive Browser / Venue Viewer / Arena Builder as a separate Venue Tools lane.
5. Mod Manager + Hook Tools only after explicit approval, because it adds runtime companion behavior and product safety boundaries.
