(function executeRule(current, previous) {

    gs.info(
        '[S3.2] Incident Webhook BR started: ' +
        current.getValue('number')
    );

    try {

        var operationType = (previous === null)
            ? 'incident.created'
            : 'incident.updated';

        var aiProcessed = false;
        var aiStatus = '';

        try {
            aiProcessed = current.getValue('ai_processed') == 'true';
        } catch (e1) { aiProcessed = false; }

        try {
            aiStatus = current.getValue('ai_status') || '';
        } catch (e2) { aiStatus = ''; }

        var category = current.getValue('category') || '';

        // ServiceNow boolean fields return "1" for true
        var active = current.getValue('active') == '1';

        var blockedStatus =
            aiStatus == 'in_progress' ||
            aiStatus == 'suggested' ||
            aiStatus == 'escalated';

        var validCategory =
            category == 'network' ||
            category == 'software' ||
            category == 'hardware' ||
            category == 'inquiry';

        if (!active) {
            gs.info('[S3.2] [SKIPPED] ' + current.getValue('number') + ' - inactive');
            return;
        }

        if (aiProcessed) {
            gs.info('[S3.2] [SKIPPED] ' + current.getValue('number') + ' - ai_processed=true');
            return;
        }

        if (blockedStatus) {
            gs.info('[S3.2] [SKIPPED] ' + current.getValue('number') + ' - ai_status=' + aiStatus);
            return;
        }

        if (!validCategory) {
            gs.info('[S3.2] [SKIPPED] ' + current.getValue('number') + ' - category=' + category);
            return;
        }

        // ---- BUILD PAYLOAD (aligned with Aliaa S3.3 contract) ----
        var payload = {
            event_id:   gs.generateGUID(),
            sys_id:     current.getUniqueValue(),
            number:     current.getValue('number'),
            event_type: operationType,
            emitted_at: new GlideDateTime().getDisplayValue()
        };

        var requestBody = JSON.stringify(payload);

        gs.info('[S3.2] Eligible incident. Payload: ' + requestBody);

        var secret = gs.getProperty('x_2215697_ai_ser_0.webhook.secret');
        if (!secret) {
            gs.error('[S3.2] Webhook secret is missing');
            return;
        }
        gs.info('[S3.2] Webhook secret exists: true');

        var signer = new x_2215697_ai_ser_0.HmacSha256();
        var signature = signer.calculate(secret, requestBody);

        gs.info('[S3.2] HMAC length: ' + signature.length);
        gs.info('[S3.2] HMAC generated successfully');

        var webhookUrl = gs.getProperty('x_2215697_ai_ser_0.webhook.url');
        if (!webhookUrl) {
            gs.error('[S3.2] Webhook URL is missing');
            return;
        }
        gs.info('[S3.2] Webhook URL exists: true');

        var request = new sn_ws.RESTMessageV2();
        request.setEndpoint(webhookUrl);
        request.setHttpMethod('POST');
        request.setRequestHeader('Content-Type', 'application/json');
        request.setRequestHeader('X-Signature', signature);
        request.setRequestBody(requestBody);

        gs.info('[S3.2] Executing async webhook for ' + current.getValue('number'));

        request.executeAsync();

        gs.info('[S3.2] executeAsync() submitted successfully for ' + current.getValue('number'));

    } catch (e) {
        gs.error('[S3.2] Incident webhook error: ' + e.message + ' | ' + e.stack);
    }

})(current, previous);