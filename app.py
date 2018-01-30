'''
MIT License

Copyright (c) 2017 cgrok

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''

import os
import hmac
import hashlib
from functools import wraps
from urllib.parse import urlencode
import asyncio

from sanic import Sanic
from sanic.response import html, text, redirect, HTTPResponse
from sanic_session import InMemorySessionInterface
from motor.motor_asyncio import AsyncIOMotorClient
from jinja2 import Environment, PackageLoader

import discord
import aiohttp
import ujson

from utils.user import User
from utils.utils import get_stack_variable, validate_github_payload, json

with open('data/config.json') as f:
    CONFIG = ujson.loads(f.read())

dev_mode = CONFIG.get('dev_mode', False)

domain = '127.0.0.1:8000' if dev_mode else 'botsettings.tk'

DEVELOPERS = [
    325012556940836864,
    271747354472873994,
    126321762483830785,
    180314310298304512
]

OAUTH2_CLIENT_ID = CONFIG.get('client_id')
OAUTH2_CLIENT_SECRET = CONFIG.get('client_secret')
OAUTH2_REDIRECT_URI = f'http://{domain}/callback'

API_BASE_URL = 'https://discordapp.com/api'
AUTHORIZATION_BASE_URL = API_BASE_URL + '/oauth2/authorize'
TOKEN_URL = API_BASE_URL + '/oauth2/token'

app = Sanic('dash')
app.static('/static', './static')

env = Environment(loader=PackageLoader('app', 'templates'))

def render_template(name, *args, **kwargs):
    template = env.get_template(name+'.html')
    request = get_stack_variable('request')
    user = None
    if request['session'].get('logged_in'):
        user = get_user(request)
    
    kwargs['request'] = request
    kwargs['session'] = request['session']
    kwargs['user'] = user
    kwargs.update(globals())
    return html(template.render(*args, **kwargs))


####################################
# Server backed session middleware #
####################################

session_interface = InMemorySessionInterface(domain=None if dev_mode else domain)

@app.middleware('request')
async def add_session_to_request(request):
    await session_interface.open(request)

@app.middleware('response')
async def save_session(request, response):
    await session_interface.save(request, response)

async def validate_token(request):
    exists = await app.db.admin.find_one({'token': request.token})
    return exists is not None
    
#############################
# Authentication decorators #
#############################

def authrequired(admin=False):
    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            valid_token = await validate_token(request)
            if valid_token:
                return await func(request, *args, **kwargs)
            if admin is False and not request['session'].get('logged_in'):
                return redirect(app.url_for('login'))
            else:
                return await func(request, *args, **kwargs)
            if admin is True and not valid_token:
                return error('Invalid authorization token provided.')
        return wrapper
    return decorator

def bot_manager():
    def decorator(func):
        @wraps(func)
        async def wrapper(request, code_name):
            bot = await app.db.metadata.find_one({'code_name': code_name})
            bot.pop('_id')
            bot.pop('bot_token', None)
            user = get_user(request)
            id = user.id
            if id in bot.get('allowed_users', []) or id == bot['owner_id'] or id in DEVELOPERS:
                return await func(request, code_name, bot, user)
            return text('you dont have acces boi')
        return wrapper
    return decorator

####################
# Server init/stop #
####################

@app.listener('before_server_start')
async def init(app, loop):
    '''Initialize app config, database and send the status discord webhook payload.'''
    app.session = aiohttp.ClientSession(loop=loop)
    app.password = CONFIG.get('password')
    app.webhook_url = CONFIG.get('webhook_url')
    app.log_url = CONFIG.get('log_url')
    mongo_client = AsyncIOMotorClient(CONFIG.get('mongo_url'))
    app.db = mongo_client.dash

    if app.webhook_url:
        await app.session.post(
            app.webhook_url, 
            json=format_embed('deploy')
            )

@app.listener('after_server_stop')
async def aexit(app, loop):
    '''Close the aiohttp client session'''
    app.session.close()

#############
# Endpoints #
#############

@app.get('/')
async def index(request):
    return render_template('index')

@app.get('/login')
async def login(request):
    if request['session'].get('logged_in'):
        request['session'].clear()
    data = {
        "scope": "identify",
        "client_id": OAUTH2_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": OAUTH2_REDIRECT_URI
    }
    return redirect(f"{AUTHORIZATION_BASE_URL}?{urlencode(data)}")

async def fetch_token(code):
    data = {
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": OAUTH2_REDIRECT_URI,
        "client_id": OAUTH2_CLIENT_ID,
        "client_secret": OAUTH2_CLIENT_SECRET
    }

    async with app.session.post(f"{TOKEN_URL}?{urlencode(data)}") as resp:
        json = await resp.json()
        return json

async def get_user_info(token):
    headers = {"Authorization": f"Bearer {token}"}
    async with app.session.get(f"{API_BASE_URL}/users/@me", headers=headers) as resp:
        return await resp.json()

def get_user(request):
    data = request['session']['user']
    return User(data=data)

@app.get('/callback')
async def oauth_callback(request):
    code = request.raw_args.get('code')
    token = await fetch_token(code)
    access_token = token.get('access_token')
    if access_token is not None:
        request['session']['access_token'] = access_token
        request['session']['logged_in'] = True
        request['session']['user'] = await get_user_info(access_token)
        return redirect(app.url_for('select_bot'))
    return redirect(app.url_for('login'))

@app.get('/logout') 
@authrequired()
async def logout(request):
    request['session'].clear()
    return redirect(app.url_for('index'))

@app.get('/bots')
@authrequired()
async def select_bot(request):
    user = get_user(request)
    bots = []

    query = {
        '$or': [{'owner_id': user.id}, 
        {'allowed_users': user.id}]
        }
    
    if user.id in DEVELOPERS:
        query = {}

    async for bot in app.db.metadata.find(query):
        bots.append(bot)

    return render_template('select-bot', user=user, bots=bots)

@app.get('/bots/<code_name>')
@authrequired()
@bot_manager()
async def dashboard(request, code_name, bot, user):
    return render_template('dash-metrics', bot=bot, user=user)

@app.post('/hooks/github')
async def upgrade(request):
    if not validate_github_payload(request):
        return text('fuck off')
    if any('[deploy]' in c['message'] for c in request.json['commits']):
        await app.session.post(app.webhook_url, json=format_embed('update'))
        app.loop.create_task(restart_later())
    return json({'success': True})

def format_embed(event):
    em = discord.Embed()
    if event == 'update':
        em.title = '[Info] Website update and restart started.'
        em.color = discord.Color.blue()
    elif event == 'deploy':
        em.title = '[Success] Website successfully deployed.'
        em.color = discord.Color.green()
    return {
        'embeds': [em.to_dict()]
        }

async def restart_later():
    app.session.close()
    command = 'sh ../dash.sh'
    os.system(f'echo {app.password}|sudo -S {command}')

if __name__ == '__main__':
    app.run() if dev_mode else app.run(host='botsettings.tk', port=80)