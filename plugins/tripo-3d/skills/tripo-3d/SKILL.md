---
name: tripo-3d
description: Generate a 3D model from a text prompt, a reference image, or an existing mesh with the Tripo connector, and deliver it as GLB, FBX, OBJ, STL, USDZ or 3MF. Use when the user asks for a 3D asset, model, mesh, prop, character or texture for a game, renderer, viewer, AR scene or 3D print — including requests like "make me a low-poly X", "turn this image into 3D", "text to 3D", "image to 3D", "multiview to 3D", "rig this character", "animate this model", "retexture this", "decimate / reduce polygons", "quad mesh", "split this model into parts", "3D print this figurine", "convert this model to FBX/GLB/OBJ/STL/USDZ/3MF", or "generate placeholder assets". Also use to re-run, convert or inspect a previous Tripo generation, and to answer questions about which Tripo model, parameter or step to use and what it costs in credits — the capability reference below replaces the official docs for that.
metadata:
  ai.workbuddy.display_name: Tripo 3D
  ai.workbuddy.display_name_en: Tripo 3D
  ai.workbuddy.description_zh: Generate textured, rig-ready 3D models from text or images; rig, animate, decimate, segment and export GLB/FBX/OBJ/STL/USDZ/3MF.
  ai.workbuddy.description_en: Generate textured, rig-ready 3D models from text or images; rig, animate, decimate, segment and export GLB/FBX/OBJ/STL/USDZ/3MF.
  ai.workbuddy.version: 0.1.3
  ai.workbuddy.author: VAST
---
# Tripo 3D

Generate engine-ready 3D assets through the Tripo 3D connector. Every capability
is an MCP tool named `tripo_*` (`tripo_text_to_3d`, `tripo_task_wait`, ...).

## Before you start

The tool list must contain the `tripo_*` tools. If it does not, the Tripo 3D
connector is not installed or not connected: tell the user to open
**Connectors → Tripo 3D** and click **Connect**, then stop. Never describe a
generation as if it had run — there is no other execution path in this connector.

## Rules

- **Wait, then judge.** Every generation or processing call returns a `task_id`
  and runs for 1–4 minutes; a `task_id` is never a result. On `success`, look at
  the preview and show it to the user before building on it. On `failed`/`banned`,
  relay `failure_reason` (and `error_code`) honestly — failed-task credits are
  refunded automatically. Never silently re-roll a disappointing result: show the
  preview and ask; re-rolling means a new task with the same prompt.
- **Credits belong to the user.** Every billed step reports `credits_consumed`.
  Check `tripo_balance` and confirm before generating more than one asset; report
  the cost afterwards. On insufficient balance give the `topup_url` from
  `tripo_balance` (it points at the International-site console) instead of retrying.
  Untextured output (`texture: false, pbr: false`) skips texture credits entirely.
- **Links expire.** Every download URL the API returns dies after about 5 minutes
  — never cache or re-print one; fetch fresh ones with `tripo_task_status`.
- **Present files, not links.** WorkBuddy can run shell commands: download the
  result into the user's project (`curl -L -o <path> "<model_url>"`) and give
  the local path in backticks — never as a clickable link (chat previews cannot
  render meshes). Show the preview image, then offer the next real action:
  reveal it in the file manager (`open -R <path>` on macOS,
  `explorer /select,<path>` on Windows) or wire it into the project.
- **Never invent parameters.** Every parameter — with limits and price — is in
  the **Capability reference** at the end. Read it instead of sending the user to
  the website. The generation model version is chosen automatically (see
  "Models" there), and the rig model from `rig_type` (see "Processing steps");
  force either only when the user asks or the rule picks wrong.

## Authorization

Tool calls fail with an authorization error until the user connects a Tripo
account. WorkBuddy handles the OAuth flow itself — clicking **Connect** on the
connector (or the first tool call) opens the authorization page in the browser
and WorkBuddy retries the call once authorized. Your job is to guide the user
through the pages — never ask for an API key in the chat:

1. The authorization page shows a one-time verification code and a button
   that opens the Tripo console on the **International site**
   developers.tripo3d.ai (email sign-in, Stripe top-up). This connector works
   with International-site accounts only — an account on the China site
   developers.tripo3d.com cannot authorize here. No account yet? Signing up
   during the flow is fine and new accounts get free credits.
2. On the console: sign in, type the code into the **"Verification code"**
   field, click **Authorize**. Nothing is ever copied or pasted into the chat.

Generations spend credits from the account the user connected. The connection
is bound to the API key the user picked on the Tripo console during
authorization (an account with no key gets `cli-default` created automatically;
with exactly one key it is used as is). Tokens refresh automatically; if a tool
returns an authorization error later, tell the user to reconnect the connector
(**Connectors → Tripo 3D → Reconnect**). To revoke access, delete that key on
the console's API Keys page.

## Workflow

1. **Create** — `tripo_text_to_3d` for prompts (Chinese or English, concrete
   nouns + style + materials), `tripo_image_to_3d` for one image,
   `tripo_multiview_to_3d` for 2–4 views. Each returns a `task_id` immediately.
   When the server strips an unsupported parameter it says so in `notes` — relay it.
2. **Wait** — call `tripo_task_wait` with the `task_id` and `timeout_seconds: 25`
   (WorkBuddy expects a tool call to answer within about 30 seconds), and call
   it again while status is still `queued`/`running`. Do not invent your own
   sleep loop.
3. **Post-process** — each step is a new billed task (create → `tripo_task_wait`)
   whose `input` is the previous task_id, a `file_token` or a public model URL:
   `tripo_texture`; `tripo_rig_check` → `tripo_rig` → `tripo_animate`;
   `tripo_convert`; `tripo_decimate`; `tripo_segment` → `tripo_mesh_complete`;
   `tripo_smart_segment`; `tripo_mesh_edit`. Arguments and constraints are in
   the Capability reference → Processing steps. For rigs leave `model` unset —
   `tripo_rig` picks the humanoid v1.0 rig for `biped` and the creature v2.5 rig
   for the other body types, and its result names the preset family
   `tripo_animate` must use (`preset:biped:*` for humanoids, `preset:walk` etc.
   for creatures). Stylization (lego / voxel / minecraft) has no tool here — say
   so instead of improvising.
4. **Deliver** — download the file into the project
   (`curl -L -o <path> "<model_url>"`) and give the local path; if the shell is
   unavailable, give the fresh `model_url`, say it is short-lived, and offer to
   refresh it on request.

## Scenario → tool chain

Pick the chain from what the user is building; every arrow is a billed task
followed by `tripo_task_wait`. GLB is the native output — a `tripo_convert`
step is only worth its credits when the target really needs another format.

- **Game prop, mobile / WebGL / many instances** — generate with
  `face_limit` ≤ 20000 (auto-selects the low-poly `P1` model) →
  `tripo_convert` `format: "FBX"` (`texture_size: 2048`) for Unity/Unreal;
  Three.js/Godot take the GLB as is.
- **Game hero asset, PC / console** — default `v3.1`, `pbr: true`,
  `texture_quality: "detailed"` → FBX only if the engine needs it.
- **Film / render / close-ups** — `v3.1` with `geometry_quality: "detailed"`
  and `texture_quality: "detailed"` (both cost extra credits).
- **3D print / figurine** — `texture: false, pbr: false` → `tripo_convert`
  `format: "STL"` (`flatten_bottom: true` for a stable base); `3MF` also works.
- **AR / iOS Quick Look** — `auto_size: true` (real-world meters) →
  `tripo_convert` `format: "USDZ"`; WebXR uses the GLB directly.
- **Animated character** — T-pose reference first (`tripo_generate_image`
  with `template: "t_pose"` turns a character image into one) →
  `tripo_image_to_3d`/`tripo_text_to_3d` → `tripo_rig_check` → `tripo_rig`
  (`rig_type` from the check; `spec: "mixamo"` for Unity Humanoid) →
  `tripo_animate` with the preset family named in the `tripo_rig` result:
  humanoids `["preset:biped:walk", "preset:biped:idle"]`, creatures (quadruped
  and the other body types) `["preset:walk", "preset:idle"]`;
  `animate_in_place: true` when game code drives movement.
- **Quads or a face cap** — `quad: true` (v3.1 or P2) is delivered as FBX and
  can never export GLTF; `face_limit` ≤ 20000 alone switches to P1, so set
  `model: "v3.1"` explicitly when the user wants v3.1 quality under a budget.
- **LOD chain** — generate once → one `tripo_decimate` per level
  (`face_limit` is a target, not a hard ceiling — say so when the project has
  a strict budget).
- **Better views of one image** — `tripo_image_to_multiview` →
  `tripo_multiview_to_3d` with `multiview_task_id`; when the user already has
  2–4 orthographic views, `tripo_multiview_to_3d` takes them directly.
- **User's existing mesh** — a public URL goes straight into any processing
  tool's `input`; a local file goes through `tripo_upload_ticket`
  (`kind: "model"`, `format: "glb"`) → `tripo_import_model`, which yields a
  reusable task_id with a preview (`.gltf` is rejected — export `.glb`).
- **Fix one region of a model** — `tripo_mesh_edit` with the model as `input`
  and a `bbox` around the region to redo (P2 pipeline, billed separately; the
  rest of the mesh is kept).
- **Not a mesh** — `tripo_image_to_splat` outputs a Gaussian-splat `.ply`
  scene for viewers, not an editable model; say so before running it.

## Inputs

- Image inputs, three routes: a **publicly reachable URL** goes straight into
  `tripo_image_to_3d` (Tripo's servers fetch it — auth-protected, region-locked
  or slow-origin links break). A signed/short-lived or uncertain URL goes
  through `tripo_upload_image` first: the server re-hosts it and returns a
  `file_token`, failing fast instead of wasting a task. A **local image file**
  (including an image the user attached to the chat) goes through the shell:
  call `tripo_upload_ticket`, then run the `how_to` curl it returns
  (`curl -sS -X POST --data-binary @<file> -H "Content-Type: application/octet-stream" "<upload_url>"`)
  and read `file_token` from the JSON response. Without a shell, ask the user
  for a public link.
- Model files (GLB/FBX/OBJ/STL, ≤150 MB) use the same ticket with
  `kind: "model"` and `format`; the `file_token` then feeds
  `tripo_import_model` or any processing tool directly.
- Task ids chain: a successful generation task is a valid `input` for every
  processing tool, so never re-upload what Tripo already has.

## Other tools

- `tripo_task_status` — fresh links for any task; `steps: true` adds the
  per-stage breakdown when a chain misbehaves.
- `tripo_task_list` — status of up to 100 task ids in one call (batches).
- `tripo_balance` / `tripo_usage` — credits left (with `topup_url`) / recent
  per-task spend, for reporting cost after a job.

---

# Capability reference

Mirrors the official API docs so the agent never has to send the user there.
Pass every parameter below as a tool argument. The server auto-fixes the
linkage rules (pbr→texture, model-specific strips, quad→FBX) and reports what
it changed in `notes`.

## Models

| `model` | use for | limits |
| --- | --- | --- |
| **v3.1** (default) | high fidelity: PC/console, film, print | full parameter set |
| **P1** | clean low-poly: mobile, UGC, ~2 s mesh | `face_limit` 50–20000; no `quad`, `smart_low_poly`, `generate_parts`, `geometry_quality`; adds `export_uv` |
| **P2** | **Preview**: P1 upgrade, low-poly **with quads** or a bigger budget | `face_limit` 48–50000 tri / 48–25000 quad; supports `quad`, still no `smart_low_poly`, `generate_parts`, `geometry_quality`; ~5× the P1 price. Wire value `P2-20260801` |
| v3.0, v2.5 | legacy, only when the user asks | v2.5 has no `geometry_quality` |

Auto-selection: low-poly words in the prompt ("low poly", "voxel", and their
Chinese equivalents) or **any `face_limit` ≤ 20000** pick P1; P2 is picked
instead when `quad: true` is also set; everything else is v3.1. P2 is Preview
and is never chosen unless `quad: true` or `model` is set explicitly.
`tripo-turbo` and `tripo-v2.0` appear in older docs but the server rejects them.

## Generation parameters

Apply to `tripo_text_to_3d` / `tripo_image_to_3d` / `tripo_multiview_to_3d`.

| param | default | notes |
| --- | --- | --- |
| `prompt`, `negative_prompt` | – | text input only; ≤1024 / ≤255 chars |
| `face_limit` | adaptive | upper bound on triangles. v3.1 any; P1 50–20000; P2 48–50000 |
| `texture`, `pbr` | `true`, `true` | `pbr=true` forces `texture=true`. `texture=false pbr=false` = bare geometry, no texture credits |
| `texture_quality` | `standard` | `standard` / `detailed` (HD, +10 credits) / `extreme` (8K, +20) / `fast` (v3.5 textures only; same price and size as `standard`; other texture versions return 1004) |
| `texture_version` | derived from `model` | pins the texture model independently of geometry: `v3.5-20260815` (newest), `v3.0-20250812` (default for v3.x and P-series), `v2.5-20250123` (default for v2.5). All generation models incl. P1/P2 |
| `delight` | `true` | v3.5 textures only (`texture_version=v3.5-20260815`): remove baked-in lighting from the reference image; `false` keeps original shading. Older texture versions ignore it |
| `geometry_quality` | `standard` | `detailed` = Ultra geometry, finer detail up to 2M faces (+20). v3.x only |
| `quad` | `false` | quad mesh (+5); **delivered as FBX** — quads cannot be stored in GLB. v3.x and P2 |
| `smart_low_poly` | `false` | hand-modelled-style low-poly topology (+10); requires `face_limit` 500–20000 tri / 500–10000 quad. v3.x only |
| `generate_parts` | `false` | editable segmented parts (+20). Requires `texture=false pbr=false` (the server flips them and warns — re-texture afterwards with `tripo_texture`); `quad` is ignored; `smart_low_poly` wins and suppresses parts. v3.x only |
| `auto_size` | `false` | scale the model to real-world metres (AR, engines) |
| `compress` | – | `geometry` = meshopt-compressed output. v3.x only |
| `model_seed`, `texture_seed`, `image_seed` | random | reproducibility: same seed → same geometry / textures / text-to-image stage. Keep `model_seed`, vary `texture_seed` to re-texture the same shape |
| `enable_image_autofix` | `false` | image input: repair a low-quality / blurry / cropped photo first (slower) |
| `texture_alignment` | `original_image` | image/multiview: `original_image` matches the picture, `geometry` matches the mesh |
| `orientation` | `default` | image/multiview: `align_image` faces the model like the input viewpoint |
| `export_uv` | `true` | P series only: `false` skips UV unwrap (faster, smaller file; UVs are created when texturing) |
| `export_orientation` | `+x` | forward axis `+x` `-x` `+y` `-y`. **Generation only**: downstream steps (texture, rig, convert…) read the default orientation and return a wrongly oriented `success` with no error. When a chain follows, leave it unset and pass `export_orientation` to the final convert step instead |

Multiview (2–4 images): `front` is mandatory and at least two views are needed;
`left`/`back`/`right` are optional, passed as named arguments (or
`multiview_task_id` for a finished `tripo_image_to_multiview` /
`tripo_edit_multiview` sheet).

## Processing steps

Every step takes a model task_id, a `file_token` or a model URL as `input`,
except: `tripo_animate` (a successful rig task), `tripo_mesh_complete` (a
successful segment task) and `tripo_smart_segment` (file_token or URL only,
never a task_id).

| tool | arguments and constraints |
| --- | --- |
| `tripo_texture` | `texture_quality` `standard`/`detailed`/`extreme`/`fast` (`fast` needs `model` v3.5); `pbr` (true); `texture_seed`; `texture_alignment`; `model` `v3.0` / `v3.0-20250812` (default) / `v3.5-20260815` (newest; unlocks `delight` and `fast`) / `v2.5`; `bake`; `part_names` (segmented models); `compress`. Guidance — exactly one of `prompt` (+ optional `style_image`), `image`, or `images` (4 views front/left/back/right). Re-textures any model, including imported files |
| `tripo_convert` | `format` `GLTF` `USDZ` `FBX` `OBJ` `STL` `3MF` (3MF = single-colour print). Mesh: `quad`, `force_symmetry` (quad only), `face_limit` (default: keep), `flatten_bottom` + `flatten_bottom_threshold` (0.01). Texture: `texture_size` (4096), `texture_format` `JPEG`/`PNG`/`WEBP`/`BMP`/`TIFF`/`TARGA`/`HDR`/`DPX`/`OPEN_EXR`, `bake` (true), `pack_uv`, `export_vertex_colors` (OBJ/GLTF only). Export: `pivot_to_center_bottom`, `scale_factor`, `auto_size`, `with_animation` (true), `animate_in_place`, `part_names`, `export_orientation`, `fbx_preset` `blender`/`3dsmax`/`mixamo` (FBX only). `quad` with `GLTF` is rejected. Any non-default option bills the complex tier (10 credits instead of 5) |
| `tripo_import_model` | GLB/GLTF/FBX/OBJ/STL ≤150 MB via `file_token` or URL (`.gltf` only as a URL — upload `.glb`) |
| `tripo_rig_check` | free. GLB input. Result: `riggable` and recommended `rig_type`: `biped` `quadruped` `hexapod` `octopod` `avian` `serpentine` `aquatic`. Gate step — not riggable → stop; riggable → rig the **original model task**, not the check task |
| `tripo_rig` | `rig_type` one of the seven above (default `biped`; take it from rig-check); `spec` `tripo`/`mixamo` (Mixamo = Unity Humanoid-compatible skeleton); `out_format` `glb`/`fbx`; `model` — `v1.0` humanoid rig (biped only, 90+ `preset:biped:*` clips) / `v2.5` creature rig (the other six body types, 16 universal presets). Picked from `rig_type` when unset (`biped` → v1.0, otherwise v2.5); the result reports the choice plus the matching preset family |
| `tripo_animate` | needs a rig task. `animations: [...]` (≤5, billed per clip); `out_format` `glb`/`fbx`; `animate_in_place` (no root motion — game code drives movement); `bake_animation` (true, glb only); `export_with_geometry` (true) |
| `tripo_segment` | `model` `v1.0-20250506` (geometry-based, default) or `v2.0-20260430` (semantic, beta) with `segmentation_granularity` `simple`/`balanced`/`detailed`, `split_by_connectivity` (true), `ref_image` (overrides the other two). Switches to v2.0 automatically when a v2-only argument is set |
| `tripo_mesh_complete` | needs a segment task. `completion_mode` `ai_completion` (default) / `quick_cap` (hole fill, cheaper); `part_names` (default all) |
| `tripo_decimate` | `face_limit` target 500–20000 tri / 500–10000 with `quad=true`; `bake` (true) bakes textures onto the low-poly; `part_names`. `model: "v1.0"` accepts up to 2 000 000 tri / 150 000 quad but requires `face_limit` and has no `bake`/`part_names`. The budget is a target, not a ceiling |
| `tripo_smart_segment` | file_token/URL only. `seg_type` `model` (existing **GLB only**, 55 credits; default) or `image` (photo → auto-model → parts, 85); `granularity` `coarse`/`medium`/`fine`; `hint` describing the parts to find. Output: part labels, a PNG mask, the segmented GLB and the inner task ids. Unlike `tripo_segment`, it is an end-to-end pipeline |
| `tripo_mesh_edit` | P2 pipeline (model fixed). `bbox` `[[x1,y1,z1],[x2,y2,z2]]` axis-aligned box in model space bounding the region to redo; `face_limit` (≥100, adaptive when omitted); `ref_image` URL or file_token for semantic guidance; `compress` `geometry`. The rest of the mesh is kept |

Animation presets depend on the rig model of the upstream rig task — read it
from the `tripo_rig` result (a `biped` rig is v1.0 unless `model` was set).
v2.5 rig (creature body types): `preset:idle` `preset:walk` `preset:run` `preset:dive`
`preset:climb` `preset:jump` `preset:slash` `preset:shoot` `preset:hurt`
`preset:fall` `preset:turn`, plus `preset:quadruped:walk` `preset:hexapod:walk`
`preset:octopod:walk` `preset:serpentine:march` `preset:aquatic:march`. v1.0 rig
(biped only, 90+ clips as `preset:biped:<name>`): `idle` `walk` `run` `jump`
`sit` `swim`, `dance_01`…`dance_06`, `greet_01`…`greet_04`, `wave_goodbye_01`,
`clap` `bow` `cry` `laugh_01`, `angry_01`…, `box_01`…`box_03`, `front_kick_01`,
`cast_a_spell`, `basketball_shot`, `golf`, `make_a_call_01`, …

## 2D steps before 3D

`tripo_generate_image` (text→image when no `input`; edit/fusion with `input`
or `inputs`), `tripo_image_to_multiview`, `tripo_edit_multiview`,
`tripo_image_to_splat`. An image task_id is a valid `input` for
`tripo_image_to_3d` — no re-upload.

- **Templates** (`template`): `t_pose` (the pre-step for rigging), `3d_enhance`
  (clean a photo before image-to-3D; image mode only), `character_completion`,
  `asset_extraction` (text mode only), `variants`, `figure`. Image editing needs
  `prompt` and/or `template`; negative prompts go inside `prompt` after `--no`.
- **Image models** (`model`): `seedream_v4` (text-to-image default; **not accepted
  by image editing**), `seedream_v5` (editing default), Google Gemini as
  `banana` (= gemini-2.5-flash, fast), `banana_pro` (= gemini-3-pro, quality),
  `banana2` (= gemini-3.1-flash, latest fast), and OpenAI `chat_image_2`,
  `chat_image_2.5_flare` (faster), `chat_image_2.5_sunburst` (edits keep
  untouched regions closer to the original). `chat_image_1` retires 2026-10-23
  and `chat_image_1.5` on 2026-12-01: pick `chat_image_2` or a 2.5 model.
  GPT-image options: `quality` `low`/`medium`/`high` (`chat_image_2`; 2.5 also
  `xhigh`/`max`; omitted = `low`); `background` `auto`/`opaque`/`transparent`
  (2.5 only; `transparent` needs `output_format=png`).
- **Several references** (`inputs`): seedream ≤4, gemini ≤10, chat_image ≤16;
  refer to them in the prompt as `[image 1]`, `[image 2]`.
- `size` `1K`/`2K`/`4K` or `WxH` (default 2048×2048; billed by tier);
  `aspect_ratio` is honoured by the gemini (`banana*`) family only; `watermark`
  by seedream only; `output_format` `png`/`jpeg`.
- `tripo_image_to_multiview` → a 4-view sheet (front/left/back/right);
  `tripo_edit_multiview` takes that task plus 1–4 `{view, prompt}` edits; either
  task feeds `tripo_multiview_to_3d` (`multiview_task_id`).
- `tripo_image_to_splat` returns a Gaussian-splat file (30 credits, ~4 min): no
  texture, rig or convert downstream — use image-to-3D when a mesh is needed.
  Input PNG/JPEG/WebP ≤20 MB, ≥256×256 px, subject clear and centred.

## Prices

Approximate list prices, so the cost can be quoted before a run (the
authoritative number is `credits_consumed` on the result; `balance` and
`credits_consumed` are decimals, not integers):

| operation | credits |
| --- | --- |
| text-to-3D, v3.1 | 10 bare / 20 textured |
| image- or multiview-to-3D, v3.1 | 20 bare / 30 textured |
| text-to-3D, P1 | 30 bare / 40 textured (P2: 100 / 110) |
| image- or multiview-to-3D, P1 | 40 bare / 50 textured (P2: 100 / 110) |
| add-ons per generation | `texture_quality=detailed` +10, `extreme` +20, `geometry_quality=detailed` +20, `quad` +5, `smart_low_poly` +10, `generate_parts` +20 |
| texture step | 10 standard / 20 detailed / 30 extreme |
| convert | 5, or 10 with any non-default option |
| decimate | 30 (v2.0) / 10 (v1.0) |
| segment / complete | 40 / 50 (`quick_cap` 30) |
| smartsegment | 85 image / 55 model |
| rig-check / rig / animate | free / 25 / 10 per clip |
| text-to-image, image editing | 5 (seedream, banana 1K, chat_image_1) – 20 (banana_pro 4K) by model and size tier |
| image-to-multiview / edit-multiview / image-to-splat | 10 / 5 per edited view / 30 |

Credits are frozen at submission and released on failure, ban or cancellation —
failed tasks are never charged. Task states: `queued` → `running` (with
`progress` 0–100) → `success` / `failed` / `banned` (content policy) /
`cancelled`; `expired` means the output files are gone and the task must be
re-run.
