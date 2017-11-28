from sanic import Sanic
from sanic.response import html
import os

app = Sanic(__name__)

@app.route('/')
async def index(request):
    return html("<h1>Kyber was here</h1>")

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=int(os.getenv('PORT', 8000)))