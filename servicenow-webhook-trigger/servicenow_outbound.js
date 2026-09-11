(function executeRule(current, previous /* null when async */) {

    var payload = {
        incident_sys_id: current.getUniqueValue(),
        number: current.getValue('number'),
        short_description: current.getValue('short_description'),
        description: current.getValue('description')
    };

    var request = new sn_ws.RESTMessageV2();
    request.setEndpoint('https://roast-molecular-banknote.ngrok-free.dev/webhook');
    request.setHttpMethod('POST');
    request.setRequestHeader('Content-Type', 'application/json');
    request.setRequestBody(JSON.stringify(payload));

    // Fire the outbound request without making the Business Rule wait
    // for the webhook response.
    request.executeAsync();

})(current, previous);
