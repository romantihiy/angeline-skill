def handler(event, context):
    response = {'text': 'Привет, пупсик', 'end_session': False}
    if 'request' in event and 'original_utterance' in event['request'] \
                and len(event['request']['original_utterance']) > 0:
        response['text']= event['request']['original_utterance']
    return {
        'version': event['version'],
        'session': event['session'],
        'response': {
            'text': response['text'],
            'end_session': response['end_session']
        },
    }