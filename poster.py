import configparser
import markdown
import logging
import re
from logging import FileHandler
from datetime import datetime, timedelta
from beem.steem import Steem
from beem.comment import Comment
from beem.wallet import MissingKeyError
from beem.account import Account, AccountDoesNotExistsException
from beem.instance import set_shared_steem_instance, shared_steem_instance
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor
from bs4 import BeautifulSoup

config = configparser.ConfigParser()
config.read('config.ini')

set_shared_steem_instance(Steem(nobroadcast=config.getboolean('GENERAL', 'testing')))
a = Account(account=config['GENERAL']['acc_name'])


class ImgExtractor(Treeprocessor):
    def run(self, doc):
        self.md.images = []
        for image in doc.findall('.//img'):
            self.md.images.append(image.get('src'))


class ImgExtExtension(Extension):
    def extendMarkdown(self, md_):
        img_ext = ImgExtractor(md_)
        md_.treeprocessors.register(img_ext, 'imgext', 0)


md = markdown.Markdown(extensions=[ImgExtExtension()])
md.images = []


def make_table():  # loading table of voted posts
    table_string = '\n| Account | Beitrag (Steemit.com) | Bild (Busy.org) | {}'\
                   '|---------|--------------| ---- | {}'\
        .format('Gewicht |\n' if config.getboolean('POSTER', 'show_weight') else '\n',
                '--- |\n' if config.getboolean('POSTER', 'show_weight') else '\n')

    latest_vote = config['POSTER']['last_post_vote']
    first = True
    posts = []
    hidden_authors = []
    try:
        with open(file=config['POSTER']['hidden_votes_file'], mode='r')as file:
            hidden_authors = file.read().split('\n')
    except FileNotFoundError as e:
        log.exception(e)

    # generate table
    if config['POSTER']['last_post_vote'] == '':
        config['POSTER']['last_post_vote'] = (datetime.now()-timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')

    for vote in a.history_reverse(start=t,
                                  stop=datetime.strptime(config['POSTER']['last_post_vote'], '%Y-%m-%dT%H:%M:%S'),
                                  only_ops=['vote']):
        log.debug(vote)
        if first:
            first = False
            latest_vote = vote['timestamp']

        if vote['voter'] != a.name:
            continue
        if vote['timestamp'] <= config['POSTER']['last_post_vote']:
            continue

        authorperm = '{}/{}'.format(vote['author'], vote['permlink'])

        if authorperm in posts:
            continue
        posts.append(authorperm)
        if vote['weight'] <= 0:
            continue
        if vote['author'] in hidden_authors:
            continue

        c = Comment(authorperm=authorperm)
        if c.is_comment() and not config.getboolean('POSTER', 'list_comments'):  # abort comment votes
            log.debug('is comment')
            continue

        link_steemit = '[{}](https://steemit.com/{})'.format(c.title
                                                             .replace('|', '-')
                                                             .replace('[', '(')
                                                             .replace(']', ')')
                                                             .replace('\n', ' '), c.authorperm)

        image = '[Kein Bild](https://busy.org/{})'.format(c.authorperm)

        # ========================================================

        try:
            image = '[![Lädt ...](https://steemitimages.com/500x0/{})](https://busy.org/{})'\
                .format(c.json_metadata['image'][0], c.authorperm)
        except KeyError or IndexError:
            log.info('No images in JSON metadata. Searching markdown image links.')
            md.convert(c.body)
            img_count = len(md.images)
            while img_count:
                if md.images[0].startswith(('http://', 'https://')):
                    image = '[![Lädt ...](https://steemitimages.com/500x0/{})](https://busy.org/{})'\
                        .format(md.images[0], c.authorperm)
                    break
                else:
                    md.images.pop(0)
            else:
                log.info('No images in markdown. Searching HTML image links.')
                soup = BeautifulSoup(c.body)
                images = []
                for link in soup.findAll('img', attrs={'src': re.compile("^http(s?)://")}):
                    images.append(link.get('src'))
                img_count = len(images)
                while img_count:
                    if images[0].startswith(('http://', 'https://')):
                        image = '[![Lädt ...](https://steemitimages.com/500x0/{})](https://busy.org/{})'\
                            .format(images[0], c.authorperm)
                        break
                    else:
                        images.pop(0)
                else:
                    log.info('No images found.')

        # ========================================================

        table_string += '| @{} | {} | {} |'.format(c.author, link_steemit, image)
        table_string += '{!s}%|\n'.format(vote['weight']/100) if config.getboolean('POSTER', 'show_weight') else '\n'

    if not config.getboolean('GENERAL', 'testing'):
        with open(file='config.ini', mode='w') as file:
            config['POSTER']['last_post_vote'] = latest_vote
            config.write(file)
    return table_string


def make_post_body():
    with open(file=config['POSTER']['body_file'], mode='r', encoding='utf-8') as file:
        post_body = file.read().\
            replace('[DATE]', date).\
            replace('[TABLE_POSTS]', make_table())
    return post_body


def publish(_title, _body, _user_beneficiaries: list = None):
    shared_steem_instance().wallet.unlock(config['GENERAL']['wallet_key'])
    try:
        if _user_beneficiaries and len(_user_beneficiaries):
            log.debug(shared_steem_instance().post(title=_title, body=_body, author=config['GENERAL']['acc_name'],
                                                   tags=config['POSTER']['tags'].replace(' ', '').split(','),
                                                   self_vote=config.getboolean('POSTER', 'self_vote'),
                                                   app="https://github.com/PortalMine/portalvotes",
                                                   beneficiaries=_user_beneficiaries))
        else:
            log.debug(shared_steem_instance().post(title=_title, body=_body, author=config['GENERAL']['acc_name'],
                                                   tags=config['POSTER']['tags'].replace(' ', '').split(','),
                                                   self_vote=config.getboolean('POSTER', 'self_vote'),
                                                   app="https://github.com/PortalMine/portalvotes"))
    except MissingKeyError as err:
        log.exception(err)
        if not config.getboolean('GENERAL', 'testing'):
            exit(1)
    shared_steem_instance().wallet.lock()


handlers = []
if config.getboolean('LOGGING', 'to_file'):
    handlers.append(FileHandler(filename=config['LOGGING']['log_file'].replace('NAME', 'poster').replace('PID', '')))
if config.getboolean('LOGGING', 'to_console'):
    handlers.append(logging.StreamHandler())

logging.basicConfig(level=config['LOGGING']['level_main'].upper(),
                    format='%(asctime)s | %(name)s -> %(levelname)s: %(message)s',
                    handlers=handlers)
del handlers

log = logging.getLogger('poster')
log.setLevel(level=config['LOGGING']['level'].upper())
log.info('Try publish.')

t = datetime.now()
date = '{!s}.{!s}.{!s}'.format(t.day, t.month, t.year)
title = config['POSTER']['title'].replace('[DATE]', date)
body = make_post_body()
if config.getboolean('GENERAL', 'testing'):
    log.info(title)
    log.info(body)

if config.has_section('POST_BENEFICIARIES'):
    user_beneficiaries = []
    user_list = config.options('POST_BENEFICIARIES')
    user_list.sort()
    for user in user_list:
        try:
            Account(account=user, full=False, lazy=True)
        except AccountDoesNotExistsException:
            log.warning('The user @{} does not exist on the block chain.')
            continue
        if config.getfloat('POST_BENEFICIARIES', user) > 0:
            user_beneficiaries.append(
                {'account': user, 'weight': int(round(config.getfloat('POST_BENEFICIARIES', user), 2) * 100)}
            )
    log.info('Beneficiaries: {!s}'.format(user_beneficiaries))
    publish(title, body, user_beneficiaries)
else:
    publish(title, body)
