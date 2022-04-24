import pymorphy2
import json
import datetime
import requests
import time
import os

def numeralparse(text):
    with open('numerals.json') as f:
        numerals = json.load(f)
    for key in list(numerals.keys())[::-1]:
        text = text.replace(key, numerals[key])
    return text

def parse(text):
    analyzer = pymorphy2.MorphAnalyzer()
    text = text.replace('-', ' ')
    text = numeralparse(text)
    for pretext in ['от', 'с', 'из', 'до', 'на', 'к', 'в']:
        text = text.replace(pretext + ' ', '')
    text = text.split(' ')
    for index, part in enumerate(text):
        if part.isdigit():
            continue
        text[index] = analyzer.parse(part)[0].inflect({'nomn'}).word
    text = ' '.join(text)
    text = text.replace('километр', 'км')
    return text

def getdate(date):
    now = datetime.datetime.now()
    year = now.year
    if 'year' in date:
        year = date['year'] if not date['year_is_relative'] else date['year'] + year
    
    month = now.month
    if 'month' in date:
        month = date['month'] if not date['month_is_relative'] else date['month'] + month

    day = now.day
    if 'day' in date:
        day = date['day'] if not date['day_is_relative'] else date['day'] + day
    
    hour = now.hour
    if 'hour' in date:
        hour = date['hour'] if not date['hour_is_relative'] else date['hour'] + hour
    
    minute = now.minute
    if 'minute' in date:
        minute = date['minute'] if not date['minute_is_relative'] else date['minute'] + minute
    
    return datetime.datetime(year, month, day, hour, minute)

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

def engine(intents):
    helptext = '''Скажи мне станцию отправления, станцию назначения и время. ''' +\
    '''Например, "Едем с Ильинской на Фабричную завтра в 9 утра"'''
    dontunderstand = 'Прости, но я не поняла твою команду. Повтори еще раз или скажи "помогите"'
    if 'YANDEX.HELP' in intents:
        return {'text': helptext, 'end_session': False}
    if 'mainintent' not in intents:
        return {'text': dontunderstand, 'end_session': False}
    
    departure = parse(intents['mainintent']['slots']['from']['value'])
    arrival = parse(intents['mainintent']['slots']['to']['value'])

    with open('moscow_region.json') as f:
        stationcodes = json.load(f)
    
    departurecode = stationcodes.get(departure)
    arrivalcode = stationcodes.get(arrival)
    if not departurecode:
       return {'text': f'''Прости, но я не знаю станцию "{departure}"''', 'end_session': False} 
    if not arrivalcode:
        return {'text': f'''Прости, но я не знаю станцию "{arrival}"''', 'end_session': False}
    
    os.environ['TZ'] = 'Europe/Moscow'
    time.tzset()
    date = datetime.datetime.now()
    if 'when' in intents['mainintent']['slots']:
        date = getdate(intents['mainintent']['slots']['when']['value'])
    
    with open('apikey.txt') as f:
        apikey = f.read()

    ticket = getticket(departurecode, arrivalcode, date, apikey)
    if not ticket:
        return {'text': 'Прости, но мне не удалось ничего найти на заданную дату и время', 'end_session': True}

    ticket = parseticket(ticket)
    text = f"Ближайший поезд прибудет к заданной дате в {addnull(ticket['date'].hour)}:{addnull(ticket['date'].minute)} " +\
        f"{addnull(ticket['date'].day)}.{addnull(ticket['date'].month)}.{addnull(ticket['date'].year)}"
    if ticket['date'].day == datetime.datetime.now().day:
        text = f"Ближайший поезд {ticket['title']} прибудет в {addnull(ticket['date'].hour)}:{addnull(ticket['date'].minute)}," +\
            f" через {int((ticket['date'] - datetime.datetime.now()).seconds / 60)} минут"
    return {'text': text, 'end_session': True}

def handler(event, context):
    response = {
        'text': 'Откуда поедем и куда?', 
        'end_session': False}
    if 'request' in event and 'original_utterance' in event['request'] \
                and len(event['request']['original_utterance']) > 0:
        try:
            response = engine(event['request']['nlu']['intents'])
        except Exception as e:
            response = {'text': e, 'end_session': False}
    return {
        'version': event['version'],
        'session': event['session'],
        'response': {
            'text': response['text'],
            'end_session': response['end_session']
        },
    }