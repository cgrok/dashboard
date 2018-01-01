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

from sanic import Sanic
from sanic.response import html, text, redirect, HTTPResponse
from sanic_session import InMemorySessionInterface
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import urlencode
import aiohttp
import discord
import asyncio
import ujson

with open('data/config.json') as f:
    CONFIG = ujson.loads(f.read())

OAUTH2_CLIENT_ID = CONFIG.get('client_id')
OAUTH2_CLIENT_SECRET = CONFIG.get('client_secret')
OAUTH2_REDIRECT_URI = 'http://127.0.0.1:8000/callback'

API_BASE_URL = 'https://discordapp.com/api'
AUTHORIZATION_BASE_URL = API_BASE_URL + '/oauth2/authorize'
TOKEN_URL = API_BASE_URL + '/oauth2/token'

app = Sanic('dash')
session_interface = InMemorySessionInterface()

@app.middleware('request')
async def add_session_to_request(request):
    await session_interface.open(request)

@app.middleware('response')
async def save_session(request, response):
    await session_interface.save(request, response)

def json(data, status=200, headers=None):
    return HTTPResponse(
        ujson.dumps(data, indent=4), 
        status=status,
        headers=headers,
        content_type='application/json'
        )

async def validate_token(request):
    exists = await app.db.admin.find_one({'token': request.token})
    return exists is not None
    
def authrequired(admin=False):
    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            valid_token = await validate_token(request)
            if valid_token:
                return await func(request, *args, **kwargs)
            if admin is False and not request['session'].get('logged_in'):
                return text('You need to be logged in to use this endpoint.')
            else:
                return await func(request, *args, **kwargs)
            if admin is True and not valid_token:
                return error('Invalid authorization token provided.')
        return wrapper
    return decorator

@app.listener('before_server_start')
async def init(app, loop):
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
    app.session.close()

@app.get('/')
async def index(request):
    return text('This is meant to be an index.html')

@app.get('/api/bots/<bot_id:int>')
@authrequired()
async def get_bot_info(request, bot_id):
    data = await app.db.bot_info.find_one({"bot_id": bot_id})
    if not data:
        return error('Invalid bot ID', 404)
    data.pop('_id')
    data.pop('bot_token')
    data.pop('bot_id')
    return json(data)

@app.post('/api/bots/<bot_id:int>')
@authrequired(admin=True)
async def set_bot_info(request, bot_id):
    data = request.json
    await app.db.bot_info.update_one(
        {"bot_id": bot_id},
        {"$set": data}, upsert=True
        )
    return json({'success': True})

@app.get('/login')
async def login(request):
    data = {
        "scope": "identify guilds",
        "client_id": OAUTH2_CLIENT_ID,
        "response_type": "code"
    }
    return redirect(f"{AUTHORIZATION_BASE_URL}?{urlencode(data)}")

@app.get('/callback')
async def oauth_callback(request):
    code = request.raw_args.get('code')
    token = await fetch_token(code)
    request['session']['logged_in'] = True
    request['session']['discord_token'] = token['access_token']
    return redirect(app.url_for('profile'))

@app.get('/logout') 
@authrequired()
async def logout(request):
    request['session'].clear()
    return text('Logged out!')

@app.get('/profile')
@authrequired()
async def profile(request):
    token = request['session']['discord_token']
    headers = {"Authorization": f"Bearer {token}"}
    user = await app.session.get(f"{API_BASE_URL}/users/@me", headers=headers)
    guilds = await app.session.get(f"{API_BASE_URL}/users/@me/guilds", headers=headers)
    return json((dict(user=await user.json(), guilds=await guilds.json())))

@app.post('/hooks/github')
async def upgrade(request):
    if not validate_payload(request):
        return error()
    app.loop.create_task(restart_later())
    return json({'success': True})

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
        print(json)
        return json

def format_embed(event):
    event = event.lower()
    em = discord.Embed(color=discord.Color.green())
    if event == 'update':
        em.title = event.title()
    elif event == 'deploy':
        cmd = r'git show -s HEAD~1..HEAD --format="[{}](https://github.com/cgrok/dash/commit/%H) %s (%cr)"'
        if os.name == 'posix':
            cmd = cmd.format(r'\`%h\`')
        else:
            cmd = cmd.format(r'`%h`')
        em.title = event.title()
        em.description = os.popen(cmd).read().strip()
    return {'embeds': [em.to_dict()]}

async def restart_later():
    await asyncio.sleep(5)
    app.session.close()
    command = 'sh ../dash.sh'
    p = os.system(f'echo {app.password}|sudo -S {command}')

def fbytes(s, encoding='utf-8', strings_only=False, errors='strict'):
    # Handle the common case first for performance reasons.
    if isinstance(s, bytes):
        if encoding == 'utf-8':
            return s
        else:
            return s.decode('utf-8', errors).encode(encoding, errors)
    if isinstance(s, memoryview):
        return bytes(s)
    else:
        return s.encode(encoding, errors)

def validate_payload(request):
    if not request.headers.get('X-Hub-Signature'):
        return False
    sha_name, signature = request.headers['X-Hub-Signature'].split('=')
    digester = hmac.new(
        fbytes(app.password), 
        fbytes(request.body),
        hashlib.sha1
        )
    generated = fbytes(digester.hexdigest())
    return hmac.compare_digest(generated, fbytes(signature))

def error(reason, status=401):
    return json({
        "error": True,
        "message": reason
        }, status=status)

if __name__ == '__main__':
    if os.getenv('VSCODE_PID'): # not on vps 
        app.run()
    else: 
        app.run(host='0.0.0.0', port=80)

