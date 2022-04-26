import json
from os.path import exists

config = {}
oldconfig = {}

if exists('config.json'):
    with open('config.json') as f:
        oldconfig = json.load(f)

config['timetablekey'] = input("Enter your timetable api key: ")
config['developerkey'] = input("Enter your deleloper api key: ")
config['projectid'] = input("Enter your project id: ")
config['maximumrequests'] = input("Enter the maximum number of requests: ")
config['admins'] = input("Enter administrator user_ids separated by &: ").split('&')

config['maximumrequests'] = int(config['maximumrequests']) if config['maximumrequests'] else 0

for key, value in config.items():
    if not value or value == ['']:
        config[key] = oldconfig.get(key)

with open('config.json', 'w') as f:
    json.dump(config, f)