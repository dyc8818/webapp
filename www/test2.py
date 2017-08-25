from aiohttp import web
import asyncio
import logging
import orm
from config import configs
from  app import auth_factory, logger_factory, response_factory, init_jinja2, datetime_filter
import coreweb

logging.basicConfig(level=logging.INFO)


async def init(loop):
    await orm.create_pool(loop, **configs['db'])

    app = web.Application(loop=loop, middlewares=[auth_factory, logger_factory, response_factory])

    init_jinja2(app, filters=dict(datetime=datetime_filter),
                path=r"./templates")  # 初始化Jinja2，这里值得注意是设置文件路径的path参数
    coreweb.add_routes(app, 'handlers')
    coreweb.add_static(app)
    srv = await loop.create_server(app.make_handler(), '127.0.0.1', 9900)
    logging.info('server started at http://127.0.0.1:9900...')
    return srv


loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()
