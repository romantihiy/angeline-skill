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

def deltastr(timedelta, addthrough=True, disable_seconds=False):
    analyzer = pymorphy2.MorphAnalyzer()
    units = [
        {'unit': 'день', 'seconds': 86400},
        {'unit': 'час', 'seconds': 3600},
        {'unit': 'минуту' if addthrough else 'минута', 'seconds': 60},
        {'unit': 'секунду' if addthrough else 'секунда', 'seconds': 1}
    ]

    if disable_seconds:
        del units[-1]

    text = ['через'] if addthrough else []  
    total_seconds = timedelta.total_seconds()
    for unit in units:
        unit_count = int(total_seconds / unit['seconds'])
        if unit_count:
            text.append(str(unit_count))
            text.append(analyzer.parse(unit['unit'])[0].\
                make_agree_with_number(unit_count).word)
        total_seconds %= unit['seconds']
    return ' '.join(text)

def getticket(departure, arrival, date, apikey):
    request = requests.get('https://api.rasp.yandex.net/v3.0/search/', 
        params={'apikey': apikey, 'from': departure, 'to': arrival, 'lang': 'ru_RU', 
            'date': date.strftime('%Y-%m-%d')})

    if not request.ok:
        return None
    
    request = request.json()
    if request['pagination']['total'] == 0:
        return None
    
    segments = request['segments']
    for index, segment in enumerate(segments):
        segment_date = datetime.datetime.strptime(segment['departure'][:-6], 
            '%Y-%m-%dT%H:%M:%S')
        if segment_date > date:
            segment['next'] = segments[index + 1] if index + 1 < len(segments) else ''
            return segment

def parseticket(ticket):
    date = datetime.datetime.strptime(ticket['departure'][:-6], '%Y-%m-%dT%H:%M:%S')
    title = ticket['thread']['title']
    platform = ''.join(filter(lambda x: x.isdigit(), ticket['departure_platform']))
    duration = ticket['duration']
    nextticket = parseticket(ticket['next']) if ticket.get('next') else ''
    return {
        'date': date, 'title': title, 'platform': platform, 'duration': duration, 
        'next': nextticket
    }

def addnull(integer):
    integer = int(integer)
    if integer < 10:
        return '0' + str(integer)
    else:
        return str(integer)

def engine(tokens, entities, intents):
    helptext = "Скажи мне станцию отправления, станцию назначения и время. " +\
    "Также ты можешь использовать команды «подробно» и «расписание». " +\
    "Например, «Едем с Ильинской на Казанский вокзал завтра в 9 утра подробно»"
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
    
    if 'schedule' in slots:
        return {
            'text': 'Вот ссылочка', 'end_session': True,
            'button': {
                'title': "Я.Расписание",
                'url':'https://rasp.yandex.ru/search/suburban/?' +\
                    f'fromId={departurecode}&toId={arrivalcode}&date={date.strftime("%Y-%m-%d")}'
            }
        }

    with open('apikey.txt') as f:
        apikey = f.read()

    ticket = getticket(departurecode, arrivalcode, date, apikey)
    if not ticket:
        return {'text': 'Прости, но мне не удалось ничего найти на заданную дату и время', 'end_session': True}

    ticket = parseticket(ticket)
    text = "Ближайший поезд прибудет в " + ticket['date'].strftime('%H:%M %d.%m.%Y')
    today = ticket['date'].day == datetime.datetime.now().day
    if today:
        deptime = f"в {ticket['date'].strftime('%H:%M')}, " +\
            deltastr(ticket['date'] - datetime.datetime.now())
        text = [
            "Ближайший поезд", ticket['title'], 
            f"прибудет на платформу {ticket['platform']}",
            deptime
        ]
        text = ' '.join(text)
    if 'detail' in slots:
        if ticket['next']:
            text += ". Следующий поезд ожидается "
            if today:
                text += deltastr(ticket['next']['date'] - datetime.datetime.now(), 
                    disable_seconds=True)
            else:
                text += "в " + ticket['next']['date'].strftime('%H:%M')
        text += ". Продолжительность поездки составит " +\
            deltastr(datetime.timedelta(seconds=ticket['duration']), False)
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
            # response = {'text': e, 'end_session': False}
            # response = {'text': traceback.format_tb(e.__traceback__), 'end_session': False}
            response = {'text': 'Ой, кажется я сломалась', 'end_session': True}
    return {
        'version': event['version'],
        'session': event['session'],
        'response': {
            'text': response['text'],
            'end_session': response['end_session'],
            'buttons': [response['button']] if response.get('button') else []
        },
    }