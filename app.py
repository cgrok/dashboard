from sanic import Sanic
from sanic.response import html
import os
from jinja2 import Environment, PackageLoader

env = Environment(loader=PackageLoader('app', 'templates'))

app = Sanic(__name__)

@app.route('/')
async def index(request):
    template = env.get_template('home.html')
    html_content = template.render()
    return html(html_content)

if __name__ == '__main__':
    app.run(
        port=int(os.getenv('PORT', 8000)),
        workers=int(os.getenv('WEB_CONCURRENCY', 1))
        )