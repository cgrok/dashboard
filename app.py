from sanic import Sanic
from sanic.response import html
from jinja2 import Environment, PackageLoader
import aiohttp
import os
import discord
import json

env = Environment(loader=PackageLoader('app', 'templates'))

app = Sanic(__name__)
env = Environment(loader=PackageLoader('app', 'templates'))

app.static('/assets', './templates/assets')
app.static('/templates', './templates')

botname = 'Statsy'

def login_required():
    def decorator(f):
        def wrapper(*args, **kwargs):
            #do shit
            pass
        return wrapper
    return decorator

@app.listener('before_server_start')
async def init(app, loop):
    app.session = aiohttp.ClientSession(loop=loop)
    with open('data/config.json') as f:
        data = json.load(f)
        app.password = data.get('password')
        app.webhook_url = data.get('webhook_url') 

@app.route('/')
async def index(request):
    print(request.path)
    template = env.get_template('dashboard.html')
    return html(template.render(
            index='active',
            botname=botname
            ))

@app.route('/bot')
async def bot(request):
    template = env.get_template('bot_profile.html')
    return html(template.render(
            bot='active',
            botname=botname
            ))

@app.route('/config')
async def config(request):
    template = env.get_template('configuration.html')
    return html(template.render(
            config='active',
            botname=botname
            ))

@app.route('/commands')
async def cmds(request):
    template = env.get_template('commands.html')
    return html(template.render(
            commands='active',
            botname=botname
            ))

def format_embed(event):
    em = discord.Embed(color=discord.Color.green())
    em.title = event.title() + ': Restarting!'
    return {'embeds': [em.to_dict()]}

@app.route('/webhook', methods=['POST'])
async def upgrade(request):
    await self.session.post(
        app.webhook_url, 
        json=format_embed('update')
        )
    command = 'sh ../dash.sh'
    p = os.system(f'echo {app.password}|sudo -S {command}')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)