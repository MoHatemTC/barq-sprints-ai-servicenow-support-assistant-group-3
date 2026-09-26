(function executeRule(current, previous) {

    gs.info(
        '[S3.2] KB Webhook BR started: ' +
        current.getUniqueValue()
    );

    try {

        var rawOp = current.operation();
        var operation;
        if (rawOp === 'delete') {
            operation = 'deleted';
        } else if (current.isNewRecord()) {
            operation = 'created';
        } else {
            operation = 'updated';
        }

        gs.info('[S3.2] KB operation determined: ' + operation);

        if (operation !== 'deleted') {
            var workflowState = '';
            try { workflowState = current.workflow_state.toString().trim(); } catch(e) { workflowState = ''; }
            if (workflowState !== 'published') {
                gs.info('[S3.2] KB event skipped - workflow_state is "' + workflowState + '" not published');
                return;
            }
        }

        var payload = {
            article_id: current.getUniqueValue(),
            number: current.number.toString(),
            operation: operation,
            timestamp: new GlideDateTime().getValue()
        };

        var requestBody = JSON.stringify(payload);

        gs.info('[S3.2] KB eligible event. Payload: ' + requestBody);

        var secret = gs.getProperty('x_2215697_ai_ser_0.webhook.secret');
        if (!secret) {
            gs.error('[S3.2] KB webhook secret is missing');
            return;
        }
        gs.info('[S3.2] KB webhook secret exists: true');

        var signer = new x_2215697_ai_ser_0.HmacSha256();
        var signature = signer.calculate(secret, requestBody);

        gs.info('[S3.2] KB HMAC length: ' + signature.length);
        gs.info('[S3.2] KB HMAC generated successfully');

        var webhookUrl = gs.getProperty('x_2215697_ai_ser_0.webhook.url');
        if (!webhookUrl) {
            gs.error('[S3.2] KB webhook URL is missing');
            return;
        }
        gs.info('[S3.2] KB webhook URL exists: true');

        var request = new sn_ws.RESTMessageV2();
        request.setEndpoint(webhookUrl);
        request.setHttpMethod('POST');
        request.setRequestHeader('Content-Type', 'application/json');
        request.setRequestHeader('X-Signature', signature);
        request.setRequestBody(requestBody);

        gs.info('[S3.2] Executing async KB webhook for ' + current.getUniqueValue());

        request.executeAsync();

        gs.info('[S3.2] KB executeAsync() submitted successfully');

    } catch (e) {
        gs.error('[S3.2] KB webhook error: ' + e.message + ' | ' + e.stack);
    }

})(current, previous);