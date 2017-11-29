from sanic import Sanic
from sanic.response import html
from jinja2 import Environment, PackageLoader
import os
from jinja2 import Environment, PackageLoader

env = Environment(loader=PackageLoader('app', 'templates'))

app = Sanic(__name__)
env = Environment(loader=PackageLoader('app', 'templates'))

app.static('/assets', './templates/assets')
app.static('/templates', './templates')

botname = 'Statsy'

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

if __name__ == '__main__':
    app.run(port=int(os.getenv('PORT', 8000)),)