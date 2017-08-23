from aiohttp import web
import asyncio
from coreweb import add_routes,add_static
from app import init_jinja2,datetime_filter,logger_factory,response_factory
import logging

logging.basicConfig(level=logging.INFO)

#编写web框架测试
async def init(loop):
    app = web.Application(loop=loop,middlewares=[logger_factory,response_factory])
    init_jinja2(app,filters=dict(datetime=datetime_filter),path = r"E:\python_workspace\awesome-python3-webapp\www\templates")#初始化Jinja2，这里值得注意是设置文件路径的path参数
    add_routes(app,'webframe_test_handler')
    add_static(app)
    srv = await loop.create_server(app.make_handler(),'127.0.0.1',9000)
    logging.info('Server started at http://127.0.0.1:9000...')
    return srv

loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()