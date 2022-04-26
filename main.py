import pymorphy2
import json
import datetime
import requests
import traceback
import time
import os

os.environ['TZ'] = 'Europe/Moscow'
time.tzset()

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

def parsedate(yandex_date):
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

def engine(request, session):
    helptext = "Скажи мне станцию отправления, станцию назначения и время. " +\
    "Также ты можешь использовать команды «подробно» и «расписание». " +\
    "Например, «Едем с Ильинской на Казанский вокзал завтра в 9 утра подробно»"
    dontunderstand = "Прости, но я не поняла твою команду. Повтори еще раз или скажи «помогите»"
    dontnow = "Прости, но я не знаю станцию «{}»"
    notfound = "Прости, но мне не удалось ничего найти на заданную дату и время"
    train = "Ближайший поезд прибудет на платформу {platform} в {datetime}"
    detail = "Продолжительность поездки составит {duration}. Следующий поезд ожидается {next}"

    intents = request['nlu']['intents']
    
    if 'YANDEX.HELP' in intents:
        return {'text': helptext, 'end_session': False}
    if 'mainintent' not in intents:
        return {'text': dontunderstand, 'end_session': False}

    tokens = request['nlu']['tokens']
    entities = request['nlu']['entities']
    slots = intents['mainintent']['slots']
    user_id = session['user']['user_id']

    with open('config.json') as f:
        config = json.load(f)
    
    for entity in entities:
        if entity['type'] == 'YANDEX.NUMBER':
            tokens[entity['tokens']['start']] = str(entity['value'])
            for index in range(entity['tokens']['start'] + 1, entity['tokens']['end']):
                tokens[index] = ''

    departure = parse(tokens[ 
        slots['from']['tokens']['start'] : slots['from']['tokens']['end']])
    arrival = parse(tokens[ 
        slots['to']['tokens']['start'] : slots['to']['tokens']['end']])
    
    with open('moscow_region.json') as f:
        stationcodes = json.load(f)
    
    departurecode = stationcodes.get(departure)
    arrivalcode = stationcodes.get(arrival)
    if not departurecode:
       return {'text': dontnow.format(departure), 'end_session': False} 
    if not arrivalcode:
        return {'text': dontnow.format(arrival), 'end_session': False}
    
    date = datetime.datetime.now()
    if 'when' in slots:
        date = parsedate(slots['when']['value'])
    
    if 'schedule' in slots:
        return {
            'text': 'Вот ссылочка', 'end_session': True,
            'button': {
                'title': "Я.Расписание",
                'url':'https://rasp.yandex.ru/search/suburban/?' +\
                    f'fromId={departurecode}&toId={arrivalcode}&date={date.strftime("%Y-%m-%d")}'
            }
        }

    ticket = getticket(departurecode, arrivalcode, date, config['timetablekey'])
    if not ticket:
        return {'text': notfound, 'end_session': True}
    ticket = parseticket(ticket)

    istoday = ticket['date'].day == datetime.datetime.now().day
    if istoday:
        train = train.format(
            platform={ticket['platform']} if ticket['platform'] else '',
            datetime=ticket['date'].strftime('%H:%M')
        )
        train += f", {deltastr(ticket['date'] - datetime.datetime.now())}"
    else:
        train = train.format(
            platform={ticket['platform']} if ticket['platform'] else '',
            datetime=ticket['date'].strftime('%H:%M %d.%m.%Y')
        )

    if 'detail' in slots:
        detail = detail.format(
            duration=deltastr(datetime.timedelta(seconds=ticket['duration']), False),
            next=
                deltastr(ticket['next']['date'] - datetime.datetime.now(), disable_seconds=True)\
                    if istoday else "в " + ticket['next']['date'].strftime('%H:%M')\
                        if ticket['next'] else "неизвестно когда"
        )
    return {'text': train + ". " + detail if 'detail' in slots else train, 'end_session': True}

def handler(event, context):
    response = {'text': 'Откуда поедем и куда?', 'end_session': False}
    try:
        if 'request' in event and 'original_utterance' in event['request'] \
                    and len(event['request']['original_utterance']) > 0:
            response = engine(event['request'], event['session'])
    except Exception as e:
        # response = {'text': e, 'end_session': False}
        # response = {'text': traceback.format_tb(e.__traceback__), 'end_session': False}
        response = {'text': 'Ой, кажется, я сломалась', 'end_session': True}
    return {
        'version': event['version'],
        'session': event['session'],
        'response': {
            'text': response['text'],
            'end_session': response['end_session'],
            'buttons': [response['button']] if response.get('button') else []
        },
    }