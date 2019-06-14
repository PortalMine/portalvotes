import logging
from logging.handlers import TimedRotatingFileHandler
import configparser
import time
import json
import os
import re

from beem.steem import Steem
from beem.account import Account
from beem.comment import Comment
from beem.blockchain import Blockchain
from beem.wallet import MissingKeyError
from beem.instance import set_shared_steem_instance, shared_steem_instance
from beemapi.exceptions import UnhandledRPCError, decodeRPCErrorMsg


config = configparser.ConfigParser()
config.read('config.ini')

set_shared_steem_instance(Steem(nobroadcast=config.getboolean('GENERAL', 'testing'), bundle=True))
a = Account(account=config['GENERAL']['acc_name'])


def vote(c):  # maybe implement curation reward evaluation and adjust voting time per author for max rewards
    log.info('Start voting routine...')
    votes = []
    try:
        votes = c.get_votes()
    except UnhandledRPCError as e:
        msg = decodeRPCErrorMsg(e).strip()
        if not re.search("Method not found", msg):
            raise e
        else:
            log.info('No votes on this post.')

    if config['GENERAL']['acc_name'] in votes:  # check if account has already voted this post
        log.info('Post already voted.')
        return False

    age = c.time_elapsed().total_seconds()
    if age > config.getfloat('VOTER', 'vote_after_minutes') * 60:
        log.info('Post is edit after voting time ({})'.format(c.authorperm))
        return False

    log.info('Preparing for post: ' + c.authorperm)
    wait = (config.getfloat('VOTER', 'vote_after_minutes') * 60) - age
    log.info('Waiting {:.2f} seconds / {:.2f} minutes.'.format(wait, wait / 60))
    time.sleep(wait)

    comment_body = ''
    if config.getboolean('VOTER', 'write_comment'):
        with open(file=config['VOTER']['comment_file'], mode='rb') as file:  # loading comment text
            comment_body = file.read().decode('iso-8859-1')
            log.info('Loaded comment text.')

    try:
        shared_steem_instance().wallet.unlock(config['GENERAL']['wallet_key'])
        c.upvote(weight=config.getfloat('VOTER', 'vote_weight'), voter=config['GENERAL']['acc_name'])  # vote
        if config.getboolean('VOTER', 'write_comment'):
            shared_steem_instance().post(title='', body=comment_body, author=config['GENERAL']['acc_name'],
                                         reply_identifier=c.authorperm,
                                         app='https://github.com/PortalMine/portalvotes')
        log.debug(shared_steem_instance().broadcast())
        shared_steem_instance().wallet.lock()
        log.info('Voted {}'.format(c.permlink))
        return True
    except MissingKeyError as e:
        log.exception(e)
        if not config.getboolean('GENERAL', 'testing'):
            exit(1)
    except Exception as e:
        log.exception(e)
        log.info('Didn\'t vote {}'.format(c.permlink))
    return False


def check_criteria(author, perm):  # vote the post
    log.info('Check criteria...')
    permlink = author + '/' + perm
    c = Comment(authorperm=permlink)

    # ===== Dynamic Users blacklist ==================================================================================
    try:
        with open(file=config['VOTER']['dynamic_blacklist_users'], mode='r') as file:  # temporary banned usernames
            check_list = file.read().split('\n')
            log.info('Loaded banned users.')
            if author in check_list:  # cancelling vote if author is on blacklist
                log.info('Author is temporary banned. ({})'.format(author))
                return False
    except FileNotFoundError:
        log.error('Failed loading temporary banned users. Continuing without checking.')

    # ===== Users whitelist ==========================================================================================
    try:
        with open(file=config['VOTER']['whitelist_users'], mode='r') as file:  # whitelisted usernames
            check_list = file.read().split('\n')
            log.info('Loaded whitelisted users.')
            if author in check_list:  # cancelling checking if author is on whitelist
                log.info('Bypass filters because author is whitelisted. ({})'.format(author))
                return vote(c)
    except FileNotFoundError:
        log.error('Failed loading whitelisted users. Continuing without checking.')

    # ===== Post length ==============================================================================================
    length = len(c.body.replace('-', '').replace('*', '').replace('_', '').split())
    if length < config.getint('VOTER', 'minimum_post_length'):
        log.info('Insufficient length. ({!s})'.format(length))
        return False

    # ===== Users blacklist ==========================================================================================
    try:
        with open(file=config['VOTER']['blacklist_users'], mode='r') as file:  # banned usernames
            check_list = file.read().split('\n')
            log.info('Loaded banned users.')
            if author in check_list:  # cancelling vote if author is on blacklist
                log.info('Author is banned. ({})'.format(author))
                return False
    except FileNotFoundError:
        log.error('Failed loading banned users. Continuing without checking.')

    # ===== Words blacklist ==========================================================================================
    try:
        with open(file=config['VOTER']['blacklist_words'], mode='rb') as file:  # banned words
            check_list = file.read().decode('UTF-8').split('\n')
            log.info('Loaded banned words.')
            post_body = c.body\
                .replace(',', ' ')\
                .replace('.', ' ')\
                .replace('!', ' ')\
                .replace('?', ' ')\
                .replace('"', ' ')\
                .replace("'", ' ').split()
            for check in check_list:  # cancelling vote if banned words are used
                if check in post_body:
                    log.info('At least one word used is banned. ({})'.format(check))
                    return False
    except FileNotFoundError:
        log.error('Failed loading banned words. Continuing without checking.')

    # ===== Author reputation ========================================================================================
    author_account = Account(account=author, full=False)

    rep = author_account.get_reputation()
    if rep < config.getfloat('VOTER', 'minimum_author_rep'):  # dumped if author rep is too low
        log.info('Author reputation too low. ({:.2f}/{})'.format(rep, config['VOTER']['minimum_author_rep']))
        return False

    # ===== Author own SP ============================================================================================
    if config.getfloat('VOTER', 'maximum_author_own_sp') >= 0:
        sp = author_account.get_steem_power(onlyOwnSP=True)
        if sp > config.getfloat('VOTER', 'maximum_author_own_sp'):  # dumped if authors own SP is too high
            log.info('Author owns too much SP. ({!s})'.format(sp))
            return False

    # ===== Banned tags ==============================================================================================
    try:
        with open(file=config['VOTER']['blacklist_tags'], mode='r') as file:  # banned tags
            check_list = file.read().split('\n')
            log.info('Loaded banned tags.')
            if c.category in check_list:  # cancelling vote if author is on blacklist
                log.info('A tag used is banned. ({})'.format(c.category))
                return False
            for tag in c.json_metadata['tags']:
                if tag in check_list:  # cancelling vote if author is on blacklist
                    log.info('A tag used is banned. ({})'.format(tag))
                    return False
    except FileNotFoundError:
        log.error('Failed loading banned tags. Continuing without checking.')

    return vote(c)


def scan():
    log.info('Scanning...')
    counter = 0
    for post in Blockchain().stream(opNames=['comment']):  # scan for posts
        try:
            if post['parent_author'] == '':
                counter += 1
                log.debug(str(counter) + ' scanned posts.')
                if counter % 10 == 0:
                    log.info('Scanned {!s} posts so far.'.format(counter))

                tags = []
                if json.loads(post['json_metadata']).get('tags'):
                    tags.extend(json.loads(post['json_metadata'])['tags'])
                if post['parent_permlink'] not in tags:
                    tags.append(post['parent_permlink'])
                log.debug('Tags: {}'.format(tags))

                for check in config['VOTER']['voted_tags'].replace(' ', '').split(','):  # search wanted tags in posts
                    if check in tags:
                        log.info('Potential post in block {!s}. ({}/{})'
                                 .format(post['block_num'], post['author'], post['permlink']))
                        if check_criteria(post['author'], post['permlink']):  # Vote if selected tags are used
                            break
                        counter = 0
                else:
                    continue
                break

        except Exception as e:
            log.exception(e)


# wait for enough voting power, then search for posts
handlers = []
if config.getboolean('LOGGING', 'to_file'):
    handlers.append(TimedRotatingFileHandler(filename=config['LOGGING']['file']
                                             .replace('PID', str(os.getpid())).replace('NAME', 'voter_normal'),
                                             when='D',
                                             interval=1,
                                             backupCount=7))
if config.getboolean('LOGGING', 'to_console'):
    handlers.append(logging.StreamHandler())

logging.basicConfig(level=config['LOGGING']['level_main'].upper(),
                    format='%(asctime)s | %(name)s -> %(levelname)s: %(message)s',
                    handlers=handlers)
del handlers

log = logging.getLogger('voting_loop')
log.setLevel(level=config['LOGGING']['level'].upper())

a.refresh()
vp = a.get_voting_power()

log.info('Process ID is {!s}'.format(os.getpid()))

while True:
    a.refresh()
    vp = a.get_voting_power()

    if vp < config.getfloat('VOTER', 'min_vp'):
        wait_for_vp = (config.getfloat('VOTER', 'min_vp') - vp) * 4320
        log.info('{} has {:.2f}%/{}% VP. Sleeping for {:.2f} seconds / {:.2f} minutes.'
                 .format(a.name, vp, config['VOTER']['min_vp'], wait_for_vp, wait_for_vp/60))
        time.sleep(wait_for_vp)
        continue

    log.info('{} has {:.2f}% VP. Not sleeping.'.format(a.name, vp))

    while vp > config.getfloat('VOTER', 'min_vp'):
        config.read('config.ini')
        a.refresh()
        vp = a.get_voting_power()
        if vp < config.getfloat('VOTER', 'min_vp'):
            break
        log.info('VP is over {}% ({:.2f}%)'.format(config['VOTER']['min_vp'], vp))
        try:
            scan()
            time.sleep(15)
        except Exception as err:
            log.exception(err)
