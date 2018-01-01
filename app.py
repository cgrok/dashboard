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

from sanic import Sanic
from sanic.response import html, text
from motor.motor_asyncio import AsyncIOMotorClient
import aiohttp
import os
import discord
import asyncio
import ujson
import hmac
import hashlib

app = Sanic(__name__)

def json(data, *args, **kwargs):
    return text(
        ujson.dumps(data, indent=4), *args, **kwargs
        )

def authrequired():
    def decorator(f):
        async def wrapper(request, *args, **kwargs):
            token = request.headers.get('Authorization')
            if not token:
                return error('Missing authentication key.')
            if not token.startswith('Bearer'):
                return error('Invalid authentication key provided.')
            exists = await app.db.admin.find_one({'token': token.replace('Bearer ', '')})
            if exists is not None:
                return await f(request, *args, **kwargs)
            else:
                return error('Invalid authentication key provided.')
        return wrapper
    return decorator

@app.listener('before_server_start')
async def init(app, loop):
    app.session = aiohttp.ClientSession(loop=loop)
    with open('data/config.json') as f:
        data = ujson.loads(f.read())
        app.password = data.get('password')
        app.webhook_url = data.get('webhook_url')
        app.log_url = data.get('log_url')
        mongo_client = AsyncIOMotorClient(data.get('mongo_url'))
        app.db = mongo_client.dash
    
    if app.webhook_url:
        await app.session.post(
            app.webhook_url, 
            json=format_embed('deploy')
            )
 
@app.route('/')
async def index(request):
    return text('Hello World')

@app.route('/api/v1')
async def version(request):
    return json({'version': "1.0.0"})


@app.get('/api/v1/bots/<owner_id:int>')
@authrequired()
async def get_bot_info(request, owner_id):
    data = await app.db.bot_info.find_one({"owner_id": owner_id})
    if not data:
        return error('Invalid owner ID', 404)
    data.pop('_id')
    return json(data)


@app.post('/api/v1/bots/<owner_id:int>')
@authrequired()
async def set_bot_info(request, owner_id):
    data = request.json
    await app.db.bot_info.update_one(
        {"owner_id": owner_id},
        {"$set": data}, upsert=True
    )
    return json({'success': True})

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

@app.post('/hooks/github')
async def upgrade(request):
    if not validate_payload(request):
        return error()
    app.add_task(restart_later())
    return text('ok', status=200)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)

