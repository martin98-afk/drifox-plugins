# Export completed presentation pages

Never export while the room is waiting for an answer or has failed. Keep the
latest complete set of final PPT page images in their original order. Do not
mix option previews, covers or older revisions into the export.

After a partial revision, combine the revised pages with the unchanged final
pages in their original positions. Do not assume `room_id` alone reconstructs
the complete deck across rounds: a beta test revised only slide 1 of 3, and
the room-only export returned just 1 page. For such decks, use the explicit
`images` list with the asynchronous display or editable path below.

## Presentation PPTX

For a complete deck from one generation round, call `designkit_export_pptx`
with the completed `room_id` and a new
`idempotency_key`. This call builds and uploads the file synchronously and can
take longer than generation-status queries. Return the real `download_url`,
`file_name` and `page_count`. Compare the returned count with the intended
page list before claiming success. Explain that page contents are images.

For a deck assembled across revision rounds, or when the installed client
cannot accommodate the synchronous call, use asynchronous export: call
`designkit_submit_pptx_export` with `export_mode="display"`, a new
`idempotency_key`, optional `title` and `images` containing the ordered actual
page URLs, names and dimensions. Query the returned `task_id` using
`designkit_query_pptx_export`. This path supports at most 50 pages. Do not
switch methods after an uncertain submission without first checking the
original task or retrying that same operation with its original key.

## Editable PPTX

Call `designkit_generate_editable_pptx` with a new `idempotency_key`, optional
`title` and `images` containing ordered actual page URLs, names and dimensions
(at most 50 pages). Poll `designkit_query_editable_pptx` with the returned
export `task_id`, which differs from the design-generation task ID.

For either asynchronous path, `pending` means wait and query again; `success`
provides `pptx_url`; `failed` provides an error. Deliver the returned
`file_name`, `page_count`, `fallback_page_count` and `warning` where present.
Never describe an editable export as exact or completely editable when the
service reports fallback pages or layout warnings.
If `fallback_page_count` is absent, report it as unavailable rather than zero.
