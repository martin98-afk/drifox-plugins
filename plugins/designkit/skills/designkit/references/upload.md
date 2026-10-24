# Upload a local attachment

1. Call `designkit_prepare_upload` with the basename `filename` and
   `media_type` (`image`, `video` or `file`). Follow its `max_bytes` limit.
2. Use WorkBuddy AI's available local-file and HTTP tools to immediately POST
   that file to the returned `upload_url` as multipart field `file`. Use the
   exact URL, method and field name returned by the tool. No OAuth header is
   needed: the short-lived URL already carries a single-use upload ticket.
3. Accept success only if HTTP succeeds, `code` is `0` and `result.url` is an
   HTTP/HTTPS URL. Submit that `result.url` with `media_type` and `filename`
   in `attachments` to create, update or answer the task.

If the local tools cannot upload files, explain that limitation and ask for a
public file URL or offer the DesignKit room link. Do not read credentials or
fall back to unauthenticated private endpoints.

The upload URL must have HTTPS, the exact path `/upload`, and one of these
hosts: `predesignkitmcp.designkit.com`, `betadesignkitmcp.designkit.com`, or
`designkitmcp.designkit.com`. Do not send a local file to another host, follow
upload redirects, add an Authorization header or print the ticket. Do not
cache, parse, rewrite or present the ticket to the user.

For `invalid_upload`, correct the multipart request and reuse the current URL
only if the response permits it. For `invalid_upload_ticket` or `upload_failed`,
request a new upload URL and retry once. Never automatically retry an upload
with the same single-use URL after an unknown result.
