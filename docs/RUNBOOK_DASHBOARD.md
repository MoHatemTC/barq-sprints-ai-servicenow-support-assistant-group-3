# ServiceNow Runbook Upload Dashboard

This optional integration lets approved support managers upload runbook PDFs to
a ServiceNow record. ServiceNow stores each file in `sys_attachment`, sends a
signed notification to FastAPI, and a Celery worker downloads the PDF through
the ServiceNow Attachment API and indexes its extracted text into the existing
`kb_articles` Qdrant collection.

## Flow

1. A manager creates a Runbook record and attaches a PDF using the standard
   ServiceNow form attachment control.
2. An asynchronous Business Rule on `sys_attachment` accepts attachments only
   for the configured Runbook table with PDF MIME type and a `.pdf` filename.
3. The rule signs a small JSON event with the same HMAC helper and secret used
   by the existing incident webhook, then posts to
   `/api/v1/documents/servicenow-attachment`.
4. FastAPI verifies the HMAC, validates the attachment ID and PDF filename,
   de-duplicates the event in Redis, and queues a Celery task.
5. The worker fetches the file from ServiceNow, enforces the configured byte
   limit, extracts text, sanitizes text/metadata, embeds chunks, and writes them
   to Qdrant with `source_type="pdf"` and attachment provenance.

The PDF is never sent in the webhook body. This keeps the ServiceNow callback
small and lets FastAPI stream the file from the authenticated ServiceNow API.

## Backend setup

1. Install/update the application and set `SERVICENOW_INSTANCE_URL`,
   `SERVICENOW_USERNAME`, and `SERVICENOW_PASSWORD` in the backend environment.
   Also set `SERVICENOW_RUNBOOK_TABLE=x_2215697_ai_ser_0_runbook_upload`.
   The integration user needs read access to the Attachment API and
   read/write access to the selected Runbook table through its Table API ACLs
   (including the `itil_admin` role or equivalent).
2. Set `SERVICENOW_WEBHOOK_SECRET` to the same secret configured in ServiceNow.
   Set `SERVICENOW_ATTACHMENT_MAX_BYTES` to the maximum accepted PDF size in
   bytes (default `26214400`, or 25 MiB).
3. Keep the app API and Celery worker running, along with Redis, Qdrant, the
   Gemini embedding configuration, and the local password-classifier service.
   Runbook chunks use the same password sanitization gate as existing KB/PDF
   ingestion.
4. Configure the public HTTPS URL with the endpoint path shown below. A local
   ServiceNow instance cannot call `localhost`; use a trusted HTTPS tunnel for
   development.

The async endpoint is:

```text
POST https://<public-host>/api/v1/documents/servicenow-attachment
Content-Type: application/json
X-Signature: <HMAC-SHA256 hex digest of the exact request body>
```

Example event:

```json
{
  "event_id": "runbook:<attachment_sys_id>",
  "attachment_sys_id": "<32-character sys_attachment sys_id>",
  "file_name": "network-recovery.pdf",
  "table_sys_id": "<32-character runbook record sys_id>",
  "title": "Network recovery",
  "category": "network",
  "runbook_notes": "Restart the gateway after recovery.",
  "emitted_at": "<ServiceNow timestamp>"
}
```

FastAPI validates `attachment_sys_id`, `table_sys_id`, `file_name`, and
`category`. It downloads by attachment sys_id; title and category are kept as
Qdrant provenance metadata. Uploader notes are read from the separate
`runbook_notes` field, indexed as metadata, and are not overwritten by worker
status messages.

## ServiceNow setup

1. Your existing table name is `x_2215697_ai_ser_0_runbook_upload`. Configure
   backend `SERVICENOW_RUNBOOK_TABLE` to this exact name. Its fields used by
   the integration are `title` (up to 120 characters), `category`
   (`network`, `software`, `hardware`, or `vpn`), `status` (`Pending`,
   `Processing`, `Ingested`, `Failed`), and `ingestion_notes` (up to 500
   characters). Add one more field, `runbook_notes` (String, up to 500
   characters), to retain the notes entered by the uploader.
2. Map the Record Producer variables to matching fields:
   `runbook_title` -> `title`, `runbook_category` -> `category`, and
   `runbook_notes` -> `runbook_notes`; set initial `status` to `Pending`.
   Keep `ingestion_notes` reserved for backend progress/resultsΓÇöthe worker
   updates that field as the status changes. Keep the manager ACLs.
   The backend integration user separately needs read access to `sys_attachment`
   and read/write access to this table through the Table API.
3. The Record Producer plus its resulting Runbook record form is the upload
   dashboard. The native mandatory attachment control requires a file, while
   the Business Rule below checks that the file is a PDF. ServiceNow stores
   the attachment in `sys_attachment`; only extracted text chunks and
   provenance metadata are sent to Qdrant.
4. Confirm the ServiceNow Script Include
   `x_2215697_ai_ser_0.HmacSha256` exists and is callable from the scoped
   Business Rule. The existing incident Business Rule in this repository
   already uses that helper, but the helper implementation is not included
   here. It must calculate lowercase/uppercase-insensitive HMAC-SHA256 hex over
   the exact JSON string without adding a prefix or newline.
5. Create/use these ServiceNow System Properties:

   | Property | Value |
   |---|---|
   | `x_2215697_ai_ser_0.webhook.secret` | Same secret as backend `SERVICENOW_WEBHOOK_SECRET`; use this exact property name in the incident, KB, and runbook rules |
   | `x_2215697_ai_ser_0.fastapi_url` | Active HTTPS ngrok base URL; the rule appends `/api/v1/documents/servicenow-attachment` |
   | `x_2215697_ai_ser_0.runbook.table` | `x_2215697_ai_ser_0_runbook_upload` (optional; this is the script default) |

6. Add a Business Rule on **sys_attachment**. Set **When** to `after`, check
   **Async**, and select **Insert** and **Update**. A Service Catalog Record
   Producer may first create the attachment against a temporary catalog
   record and then re-associate it with the produced Runbook row by updating
   `table_name`/`table_sys_id`; an insert-only rule can miss that transition.
   The script checks the parent table and PDF type at execution time, so it
   ignores updates while the attachment is still on another table. Use the
   script in
   [`servicenow/scripts/runbook_attachment.js`](../servicenow/scripts/runbook_attachment.js).
   It checks both `table_name` and `content_type == application/pdf`, signs
   the exact JSON request body, records `Processing` before POSTing to FastAPI,
   and changes to `Failed` on an exception or non-2xx response. Setting
   `Processing` before the call avoids a fast worker's `Ingested` update being
   overwritten after the webhook returns.
7. Ensure outbound REST calls from ServiceNow can reach the HTTPS host. Do not
   put the secret in the URL, event body, or logs.

## Verify end to end

1. Put these values in the backend `.env` (keep the other model, Redis,
   Qdrant, and classifier settings):

   ```dotenv
   SERVICENOW_INSTANCE_URL=https://<your-instance>.service-now.com
   SERVICENOW_USERNAME=<dedicated-integration-user>
   SERVICENOW_PASSWORD=<integration-user-password>
   SERVICENOW_WEBHOOK_SECRET=<same-secret-as-ServiceNow-property>
   SERVICENOW_RUNBOOK_TABLE=x_2215697_ai_ser_0_runbook_upload
   SERVICENOW_ATTACHMENT_MAX_BYTES=26214400
   ```

   Do not commit `.env`. The backend uses these ServiceNow credentials to
   download `sys_attachment` and update the Runbook record. They are different
   from the HMAC secret used to authenticate inbound webhooks.
2. Recreate/start the services after changing `.env`, then check API health:

   ```powershell
   docker compose up -d --build api worker
   Invoke-RestMethod http://localhost:8000/health
   ```

   Expect `status: ok`. Watch the API and worker logs in another terminal:

   ```powershell
   docker compose logs --tail 100 -f api worker
   ```

3. In ServiceNow, set `x_2215697_ai_ser_0.fastapi_url` to the current ngrok
   **base URL**, e.g. `https://<your-subdomain>.ngrok-free.app` (do not add the
   endpoint path). Verify `x_2215697_ai_ser_0.webhook.secret` exactly matches
   `SERVICENOW_WEBHOOK_SECRET`, and that ngrok forwards to host port 8000.
   The incident and KB rules must also read this exact dotted property name.
4. Submit a Record Producer form with a PDF. Verify the created `sys_attachment`
   has `table_name=x_2215697_ai_ser_0_runbook_upload`, `table_sys_id` set to the
   produced Runbook sys_id, `content_type=application/pdf`, and a `.pdf`
   `file_name`. Confirm the Business Rule runs and FastAPI returns HTTP 202.
5. Confirm the Runbook status becomes `Ingested` and its notes report the
   page/chunk count. Search for a distinctive PDF sentence using the existing
   retrieval flow; the Qdrant payload should include `source_type="pdf"`,
   `file_name`, and `attachment_sys_id`.
6. Upload a non-PDF file and verify the rule does not notify FastAPI. Re-send
   the same attachment event and verify Redis de-duplicates it.

## Troubleshooting the integration

- **The rule did not run:** Inspect the attachment's `table_name`,
  `table_sys_id`, `content_type`, and `file_name`. Record Producer attachments
  must end up attached to the produced Runbook row, not a temporary catalog
  record. Verify the Business Rule is active, async, and set to both Insert
  and Update. The update event after re-association is what should produce
  the callback if the initial insert was on a catalog table.
- **`Parent runbook record not found`:** The rule has not reached FastAPI yet:
  it returns before making the outbound request. Open the `sys_attachment`
  record identified in the log and compare its `table_name` and
  `table_sys_id` with the actual Runbook record. `table_name` must equal the
  configured Runbook table and `table_sys_id` must be the sys_id of a record
  that exists in that table. If the attachment is initially associated with a
  catalog record, make sure the rule runs on Update as well as Insert so it
  retries after ServiceNow changes the attachment's parent. Use the diagnostic
  error log's `table_sys_id` and `expected_table` values; the attachment's own
  sys_id is not the parent record sys_id.
- **HTTP 401:** The backend secret and ServiceNow property differ, or
  `HmacSha256.calculate(secret, requestBody)` is not returning plain
  HMAC-SHA256 hex for the exact JSON string passed to `setRequestBody`. Sign
  and send the same string; do not serialize it again in between. Confirm all
  ServiceNow rules use `x_2215697_ai_ser_0.webhook.secret` and the backend
  environment has that same value in `SERVICENOW_WEBHOOK_SECRET`.
- **HTTP 404:** Check that `fastapi_url` is the active ngrok base URL and the
  tunnel forwards to port 8000. The rule appends
  `/api/v1/documents/servicenow-attachment`.
- **HTTP 422:** Read the response detail in ServiceNow logs. Both attachment
  and parent record IDs must be 32-character sys_ids; the name must end in
  `.pdf`; title length is at most 120; category must be `network`, `software`,
  `hardware`, or `vpn`.
- **HTTP 202 but still `Processing`:** Check worker logs and verify the worker
  shares the API's Redis broker. Common causes include missing backend
  ServiceNow ACLs/credentials, model or Qdrant configuration errors, and PDFs
  with no selectable text.
- **The row becomes `Failed`:** `ingestion_notes` gives a safe summary; check
  worker logs for details. Ensure the backend integration user can update the
  `status` and `ingestion_notes` fields.

## Supported files and operational notes

- The configured maximum size defaults to 25 MiB and is enforced while
  downloading, even when ServiceNow omits `Content-Length`.
- The automatic path in this repository extracts selectable text with
  PyMuPDF. It does **not** currently run the multimodal/OCR pipeline described
  in the proposed infrastructure summary. Scanned/image-only PDFs are
  rejected with a visible Celery task error; OCR/multimodal extraction
  remains available through the existing manual `scripts/ingest_pdf.py`
  workflow.
- The current rule runs on attachment insert. To re-index changed content,
  delete the old attachment and upload a new one so ServiceNow creates a new
  attachment sys_id and a new idempotency key.
- Failed background tasks are visible in worker logs and should set the
  Runbook record to `Failed`. A notification being accepted by FastAPI means
  it was queued, not that indexing completed.
- Apply the same access controls and retention policies to the Runbook table
  and its attachments as to the underlying operational documentation.
