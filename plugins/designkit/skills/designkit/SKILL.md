---
name: designkit
description: Create and revise presentations, posters, product images and other visual designs with the connected DesignKit account. Follow asynchronous progress, answer design questions, show generated images and download presentation or editable PPTX files. Use when the user asks DesignKit to create, revise or export a design.
---
# DesignKit

Use the connected DesignKit MCP tools. Before submitting a brief or uploading
attachments, explain that DesignKit will process that brief and those files.
Use the user's language for conversation and include their requested output
language in the design brief.

## Connection

The connector uses the user's DesignKit account through MCP OAuth. If tools
are missing or authorization fails, ask the user to connect or reconnect
DesignKit in WorkBuddy AI. Never request a token, cookie or password, read
client credential files, install the DesignKit CLI, or call private account APIs.
Do not set `req_model_path`; use the service's default model routing.

## Create or revise

1. Use the user's brief, files, page count, language and visual preferences.
   Clarify only missing information that materially affects the requested output.
2. Call `designkit_create_task` for a new design. Use `designkit_update_task`
   with the existing `room_id` for revisions to that design.
3. Supply a unique 8–128 character ASCII `idempotency_key` for each new write
   operation. Retry an uncertain operation with the same key and identical
   arguments. Never create a second room to recover from an uncertain response.
4. Save the returned `room_id`, `task_id` and `room_url`.

For presentations, keep the current final image URL for each slide in page
order. After a partial revision completes, replace only the revised pages and
retain the unchanged pages. Do not assume the latest response contains the
whole deck. If page identity or order is unclear, clarify before exporting.

## Attachments

Use only files or public HTTP/HTTPS URLs supplied for the current task. Never
pass local paths or `file://` URLs as attachments. For local files, read
[the upload procedure](references/upload.md). Preserve file order and names.

Supported uploads: JPG/JPEG/PNG images; MP4/MOV videos; XLS/XLSX, DOC/DOCX,
TXT, PDF, PPT/PPTX, MP3/WAV, CSV and MD files. Images and ordinary files are
limited to 20 MiB each; videos to 200 MiB. Submit at most 10 images, or one
video with at most 9 images, or one ordinary file alone. Do not mix ordinary
files with images or videos, convert files without permission, or silently
drop attachments.

## Follow progress and questions

Call `designkit_get_artifacts` with `room_id` and initially `after_seq=-1`.
Save `max_seq` and use it as the next `after_seq`; do not send a parameter
named `max_seq`. Keep the last confirmed cursor across network failures.

Show newly returned artifacts first, then follow `next_action`:

| Value | Action |
| --- | --- |
| `poll` | Wait a few seconds and query the same room. Share meaningful progress; avoid tight polling. |
| `reply` | Stop polling and show the returned questions, options and preview images. Wait for the user's answer. |
| `recharge` | Stop; explain the returned account limitation. Offer the returned account link only as needed. Never start a new room to bypass it. |
| `done` | Check `terminal_outcome`. A failed task is not successful even if `is_complete` is true. Deliver actual artifacts and the room link. |

For an answer, call `designkit_answer_task` using the returned interaction
context: preserve `task_id`, `sub_task_id` and `last_request_id` (sent as
`request_id`). Use `message` for text, `select_option_ids` as an array of
arrays of actual option IDs, or `custom_card_answer` with the returned
`card_type`, `card_id` and the user's choices. Never invent IDs or confirm a
review on the user's behalf. Resume queries after the answer succeeds.

After the user resolves the account limitation and asks to continue, call
`designkit_resume_after_recharge` with the original `room_id`, `task_id` and
returned `resume_after_seq` as `seq_id`. Then query that same room from that
cursor. Do not replace the interrupted task with a new design.

## Show results

Use actual `structuredContent.artifacts` and MCP `resource_link` results.
Show each new image with its original-image link when the client supports
inline previews; otherwise provide a clickable original-image link and the
`room_url`. Keep the full URL and all query parameters. Do not claim a preview
rendered merely because a link was returned. Do not call `designkit_show_images`:
that tool and its embedded gallery belong to the ChatGPT channel.

Use video `media_url` for the video itself; `media_cover_url` is only a cover.
For other files, provide the actual download link. Do not repeat previously
delivered artifacts or invent a file, image, URL or completion status.

## PowerPoint export

After a presentation completes, show its actual pages and offer both options:

- **Presentation PPTX:** image-based pages that preserve the design; individual
  text and layout elements are not editable.
- **Editable PPTX:** attempts editable text and layout. Text/layout can differ;
  failed pages may use image fallback. It usually takes longer.

Honor an explicit format request; if unspecified, ask the user to choose before
exporting. Read [the export procedure](references/pptx.md) after the choice.
For a deck assembled across revision rounds, export its explicit current page
list; a room-only export may contain only the revised subset.

## Errors and support

Use the current tool schema as the parameter contract. Correct invalid
arguments from returned errors; stop and reconnect on authentication errors.
For transient failures, retry reads from the last cursor and uncertain writes
with their original key. If a write has no known result or room, explain that
uncertainty instead of submitting another design.

Call `designkit_feedback` with the actual `room_id` when the user requests
support. It returns a support link and does not send a message or submit a
design revision. Use `designkit_update_task` for revisions. These tools do not
send email, publish designs to social networks, or purchase products.
