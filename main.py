import pymorphy2
import json
import datetime
import requests
import time
import os
import traceback

def parse(tokens):
    analyzer = pymorphy2.MorphAnalyzer()
    stopwords = ['от', 'с', 'из', 'до', 'на', 'к', 'в']
    tokens = list(filter(lambda x: x and x not in stopwords, tokens.copy()))
    for index, token in enumerate(tokens):
        nomn = analyzer.parse(token)[0].inflect({'nomn'})
        if nomn:
            tokens[index] = nomn.word
        if tokens[index] == 'километр':
            tokens[index] = 'км'
    text = ' '.join(tokens)
    return text

def getdate(yandex_date):
    date = datetime.datetime.now()
    
    units = [
        {'unit' : 'year', 'minutes': 525600, 'argument': {'year': yandex_date.get('year')}},
        {'unit' : 'month', 'minutes': 43200, 'argument': {'month': yandex_date.get('month')}},
        {'unit' : 'day', 'minutes': 1440, 'argument': {'day': yandex_date.get('day')}},
        {'unit' : 'hour', 'minutes': 3600, 'argument': {'hour': yandex_date.get('hour')}},
        {'unit' : 'minute', 'minutes': 1, 'argument': {'minute': yandex_date.get('minute')}}
    ]
    for unit in units:
        if unit['unit'] in yandex_date:
            if yandex_date[unit['unit'] + '_is_relative']:
                date += datetime.timedelta(minutes=unit['minutes']*yandex_date[unit['unit']])
            else:
                date = date.replace(**unit['argument'])
    return date

def getticket(departure, arrival, date, apikey):
    request = requests.get('https://api.rasp.yandex.net/v3.0/search/', 
        params={'apikey': apikey, 'from': departure, 'to': arrival, 'lang': 'ru_RU', 
            'date': date.strftime('%Y-%m-%d')})

    if not request.ok:
        return None
    
    request = request.json()
    if request['pagination']['total'] == 0:
        return None
    
    for segment in request['segments']:
        segment_date = datetime.datetime.strptime(segment['departure'][:-6], 
            '%Y-%m-%dT%H:%M:%S')
        if segment_date > date:
            return segment

def parseticket(ticket):
    date = datetime.datetime.strptime(ticket['departure'][:-6], '%Y-%m-%dT%H:%M:%S')
    title = ticket['thread']['title']
    return {'date': date, 'title': title}

def addnull(integer):
    integer = int(integer)
    if integer < 10:
        return '0' + str(integer)
    else:
        return str(integer)

def engine(tokens, entities, intents):
    helptext = '''Скажи мне станцию отправления, станцию назначения и время. ''' +\
    '''Например, "Едем с Ильинской на Фабричную завтра в 9 утра"'''
    dontunderstand = 'Прости, но я не поняла твою команду. Повтори еще раз или скажи "помогите"'
    
    os.environ['TZ'] = 'Europe/Moscow'
    time.tzset()

    if 'YANDEX.HELP' in intents:
        return {'text': helptext, 'end_session': False}
    if 'mainintent' not in intents:
        return {'text': dontunderstand, 'end_session': False}
    
    for entity in entities:
        if entity['type'] == 'YANDEX.NUMBER':
            tokens[entity['tokens']['start']] = str(entity['value'])
            for index in range(entity['tokens']['start'] + 1, entity['tokens']['end']):
                tokens[index] = ''

    slots = intents['mainintent']['slots']

    departure = parse(tokens[ 
        slots['from']['tokens']['start'] : slots['from']['tokens']['end']])
    arrival = parse(tokens[ 
        slots['to']['tokens']['start'] : slots['to']['tokens']['end']])

    with open('moscow_region.json') as f:
        stationcodes = json.load(f)
    
    departurecode = stationcodes.get(departure)
    arrivalcode = stationcodes.get(arrival)
    if not departurecode:
       return {'text': f'''Прости, но я не знаю станцию "{departure}"''', 'end_session': False} 
    if not arrivalcode:
        return {'text': f'''Прости, но я не знаю станцию "{arrival}"''', 'end_session': False}
    
    date = datetime.datetime.now()
    if 'when' in slots:
        date = getdate(slots['when']['value'])

    with open('apikey.txt') as f:
        apikey = f.read()

    ticket = getticket(departurecode, arrivalcode, date, apikey)
    if not ticket:
        return {'text': 'Прости, но мне не удалось ничего найти на заданную дату и время', 'end_session': True}

    ticket = parseticket(ticket)
    text = f"Ближайший поезд прибудет к заданной дате в {addnull(ticket['date'].hour)}:{addnull(ticket['date'].minute)} " +\
        f"{addnull(ticket['date'].day)}.{addnull(ticket['date'].month)}.{addnull(ticket['date'].year)}"
    if ticket['date'].day == datetime.datetime.now().day:
        timeleft = int((ticket['date'] - datetime.datetime.now()).seconds / 60)
        unit = 'минут'
        if timeleft == 1 or timeleft % 10 == 1:
            unit = 'минуту'
        if timeleft > 1 and timeleft < 5 or timeleft % 10 > 1 and timeleft % 10 < 5 and timeleft > 20:
            unit = 'минуты'
        text = f"Ближайший поезд {ticket['title']} прибудет в {addnull(ticket['date'].hour)}:{addnull(ticket['date'].minute)}," +\
            f" через {timeleft} {unit}"
    return {'text': text, 'end_session': True}

def handler(event, context):
    response = {
        'text': 'Откуда поедем и куда?', 
        'end_session': False}
    if 'request' in event and 'original_utterance' in event['request'] \
                and len(event['request']['original_utterance']) > 0:
        try:
            response = engine(event['request']['nlu']['tokens'],
                event['request']['nlu']['entities'], 
                    event['request']['nlu']['intents'])
        except Exception as e:
            response = {'text': e, 'end_session': False}
            # response = {'text': traceback.format_tb(e.__traceback__), 'end_session': False}
            # response = {'text': 'Ой, кажется я сломалась', 'end_session': True}
    return {
        'version': event['version'],
        'session': event['session'],
        'response': {
            'text': response['text'],
            'end_session': response['end_session']
        },
    }