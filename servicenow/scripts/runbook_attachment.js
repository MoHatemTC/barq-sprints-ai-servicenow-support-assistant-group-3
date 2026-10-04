(function executeRule(current, previous) {
    var attachmentId = current.getUniqueValue();
    var fileName = current.getValue('file_name') || '';
    var tableName = current.getValue('table_name') || '';
    var contentType = current.getValue('content_type') || '';

    gs.info(
        '[Runbook ingestion] sys_attachment rule fired; table=' +
        tableName + '; content_type=' + contentType
    );

    if (!/\.pdf$/i.test(fileName)) {
        gs.info('[Runbook ingestion] Ignored attachment because filename is not PDF');
        return;
    }

    var allowedTable = gs.getProperty(
        'x_2215697_ai_ser_0.runbook.table',
        'x_2215697_ai_ser_0_runbook_upload'
    );
    if (
        tableName !== allowedTable ||
        contentType !== 'application/pdf'
    ) {
        gs.info(
            '[Runbook ingestion] Ignored attachment; expected table=' +
            allowedTable + ' and content_type=application/pdf'
        );
        return;
    }

    var recordId = current.getValue('table_sys_id') || '';
    var runbook = new GlideRecord(allowedTable);
    if (!runbook.get(recordId)) {
        gs.error(
            '[Runbook ingestion] Parent runbook record not found; attachment=' +
            attachmentId + '; table_name=' + tableName +
            '; table_sys_id=' + recordId +
            '; expected_table=' + allowedTable
        );
        return;
    }

    var payload = {
        event_id: 'runbook:' + attachmentId,
        attachment_sys_id: attachmentId,
        file_name: fileName,
        runbook_sys_id: recordId,
        table_sys_id: recordId,
        title: runbook.getValue('title') || '',
        category: runbook.getValue('category') || '',
        runbook_notes: runbook.getValue('runbook_notes') || '',
        emitted_at: new GlideDateTime().getValue()
    };
    var requestBody = JSON.stringify(payload);
    var secret = gs.getProperty('x_2215697_ai_ser_0.webhook.secret');
    var baseUrl = gs.getProperty('x_2215697_ai_ser_0.fastapi_url');

    if (!secret || !baseUrl) {
        gs.error('[Runbook ingestion] Webhook URL or signing secret is missing');
        return;
    }

    try {
        var endpointPath = '/api/v1/documents/servicenow-attachment';
        var webhookUrl = baseUrl.replace(/\/+$/, '');
        if (webhookUrl.slice(-endpointPath.length) !== endpointPath) {
            webhookUrl += endpointPath;
        }

        var signer = new x_2215697_ai_ser_0.HmacSha256();
        var signature = signer.calculate(secret, requestBody);
        var request = new sn_ws.RESTMessageV2();
        request.setEndpoint(webhookUrl);
        request.setHttpMethod('POST');
        request.setRequestHeader('Content-Type', 'application/json');
        request.setRequestHeader('X-Signature', signature);
        request.setRequestBody(requestBody);
        request.setHttpTimeout(15000);

        // The rule also runs on Update. Do not reset a record the backend has
        // already moved to Processing/Ingested: the backend de-duplicates repeat
        // events per attachment and would never correct the status again.
        var currentStatus = runbook.getValue('status') || '';
        if (currentStatus !== 'Processing' && currentStatus !== 'Ingested') {
            runbook.status = 'Processing';
            runbook.ingestion_notes = 'PDF notification sent; waiting for backend ingestion.';
            runbook.update();
        }

        var response = request.execute();
        var responseCode = response.getStatusCode();
        if (responseCode < 200 || responseCode >= 300) {
            runbook.status = 'Failed';
            runbook.ingestion_notes = 'FastAPI rejected the upload notification (HTTP ' + responseCode + ').';
            runbook.update();
            gs.error('[Runbook ingestion] FastAPI returned HTTP ' + responseCode + ' for attachment ' + attachmentId);
            return;
        }

        gs.info('[Runbook ingestion] Queued PDF attachment ' + attachmentId);
    } catch (e) {
        runbook.status = 'Failed';
        runbook.ingestion_notes = 'Could not notify the ingestion backend. Check ServiceNow system logs.';
        runbook.update();
        gs.error('[Runbook ingestion] Failed to send attachment ' + attachmentId + ': ' + e.message);
    }
})(current, previous);
