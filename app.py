from sanic import Sanic
from sanic.response import html
import os

app = Sanic(__name__)

@app.route('/')
async def index(request):
    return html("<h1>Kyber was here</h1>")

if __name__ == '__main__':
    print(os.environ)
    app.run(
        port=int(os.getenv('PORT', 8000))
        workers=int(os.getenv('WEB_CONCURRENCY', 1))
        )