import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime, timedelta
import configparser
import random
import time
import os

from beem.steem import Steem
from beem.comment import Comment
from beem.instance import set_shared_steem_instance, shared_steem_instance
from beem.account import Account, AccountDoesNotExistsException


config = configparser.ConfigParser()
config.read('config.ini')

set_shared_steem_instance(Steem(nobroadcast=config.getboolean('GENERAL', 'testing'), bundle=True))
a = Account(account=config['GENERAL']['acc_name'])


def hundred_voter():
    authors = []
    with open(file=config['VOTER']['throw_votes_authors'], mode='r') as f:
        for line in f:
            line = line.replace('\n', '').replace('@', '')
            if len(line) >= 3:
                authors.append(line)

    random.shuffle(authors)
    log.info('Authors list: {}'.format(authors))

    comment_body = ''
    if config.getboolean('VOTER', 'throw_write_comment'):
        with open(file=config['VOTER']['throw_comment_file'], mode='rb') as file:  # loading comment text
            comment_body = file.read().decode('iso-8859-1')
            log.info('Loaded comment text.')

    for author in authors:
        try:
            for post in Account(author).history_reverse(stop=datetime.now()-timedelta(days=5), only_ops=['comment']):
                if post.get('parent_author') != '':
                    continue
                a_perm = '{}/{}'.format(author, post.get('permlink'))
                log.info(a_perm)
                c = Comment(authorperm=a_perm)
                if a.name in c.get_votes():
                    log.info('Already voted.')
                    continue

                log.info('Try vote on {}'.format(c.authorperm))
                shared_steem_instance().wallet.unlock(config['GENERAL']['wallet_key'])
                c.vote(weight=config.getfloat('VOTER', 'throw_votes_pct'), account=a.name)
                if config.getboolean('VOTER', 'write_comment'):
                    c.reply(body=comment_body, author=config['GENERAL']['acc_name'])
                log.debug(shared_steem_instance().broadcast())
                shared_steem_instance().wallet.lock()
                return True
        except AccountDoesNotExistsException:
            log.info('Account {} does not exist.'.format(author))
            continue
    else:
        log.info('Nothing found to burn vote.')
        return False


handlers = []
if config.getboolean('LOGGING', 'to_file'):
    handlers.append(TimedRotatingFileHandler(filename=config['LOGGING']['file']
                                             .replace('PID', str(os.getpid())).replace('NAME', 'voter_high'),
                                             when='D',
                                             interval=1,
                                             backupCount=7))
if config.getboolean('LOGGING', 'to_console'):
    handlers.append(logging.StreamHandler())

logging.basicConfig(level=config['LOGGING']['level_main'].upper(),
                    format='%(asctime)s | %(name)s -> %(levelname)s: %(message)s',
                    handlers=handlers)
del handlers

log = logging.getLogger('hundreds_loop')
log.setLevel(level=config['LOGGING']['level'].upper())

a.refresh()
vp = a.get_voting_power()

log.info('Process ID is {!s}'.format(os.getpid()))

while True:
    a.refresh()
    vp = a.get_voting_power()

    if vp < config.getfloat('VOTER', 'throw_votes_vp'):
        wait_for_vp = (config.getfloat('VOTER', 'throw_votes_vp') - vp) * 4320
        log.info('{} has {:.2f}%/{}% VP. Sleeping for {:.2f} seconds / {:.2f} minutes / {:.2f} hours.'
                 .format(a.name, vp, config['VOTER']['throw_votes_vp'],
                         wait_for_vp, wait_for_vp / 60, wait_for_vp / 3600))
        time.sleep(wait_for_vp)
        continue

    log.info('{} has {:.2f}% VP. Not sleeping.'.format(a.name, vp))

    while vp > config.getfloat('VOTER', 'throw_votes_vp'):
        config.read('config.ini')
        a.refresh()
        vp = a.get_voting_power()
        if vp < config.getfloat('VOTER', 'throw_votes_vp'):
            break
        log.info('VP is over {}% ({:.2f}%)'.format(config['VOTER']['throw_votes_vp'], vp))
        try:
            if hundred_voter():
                time.sleep(15)
            else:
                time.sleep(config.getfloat('VOTER', 'throw_votes_refresh_time')*60)
        except Exception as e:
            log.exception(e)
