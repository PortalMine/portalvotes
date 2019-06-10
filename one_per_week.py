import configparser

from beem.steem import Steem
from beem.account import Account
from datetime import datetime, timedelta

config = configparser.ConfigParser()
config.read('config.ini')

t = datetime.now()
a = Account(account=config['GENERAL']['acc_name'], steem_instance=Steem(node='https://api.steemit.com', nobroadcast=config.getboolean('GENERAL', 'testing')))

block_authors = []

for vote in a.history_reverse(start=t, stop=t-timedelta(days=7), only_ops=['vote']):
    if vote.get('voter') == config['GENERAL']['acc_name']:
        if vote.get('author') in block_authors:
            continue
        block_authors.append(vote.get('author'))

print(len(block_authors))

with open(file=config['VOTER']['dynamic_blacklist_users'], mode='w') as file:
    for auth in block_authors:
        file.write('{}\n'.format(auth))
