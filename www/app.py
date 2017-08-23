import logging;

logging.basicConfig(level=logging.INFO)
import asyncio, time, json, os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
import orm
from coreweb import add_routes, add_static
from aiohttp import web
from handlers import cookie2user, COOKIE_NAME


def init_jinja2(app, **kw):
    logging.info('init jinja2')
    options = dict(autoescape=kw.get('autoescape', True),
                   block_start_string=kw.get('block_start_string', '{%'),
                   block_end_string=kw.get('block_end_string', '%}'),
                   variable_start_string=kw.get('variable_start_string', '{{'),
                   variable_end_string=kw.get('variable_end_string', '}}'),
                   auto_reload=kw.get('auto_reload', True)

                   )
    path = kw.get('path', None)
    if path == None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
    logging.info('set jinja2 template path: %s' % path)
    env = Environment(loader=FileSystemLoader(path), **options)
    filters = kw.get('filters', None)
    if filters is not None:
        for name, f in filters.items():
            env.filters[name] = f
    app['__templating__'] = env


def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'1分钟前'
    if delta < 3600:
        return u'%s分钟前' % (delta // 60)
    if delta < 86400:
        return u'%s小时前' % (delta // 3600)
    if delta < 604800:
        return u'%s天前' % (delta // 86400)
    dt = datetime.fromtimestamp(t)
    return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)


async def logger_factory(app, handler):  # 协程，两个参数
    async def logger_middleware(request):  # 协程，request作为参数
        logging.info('Request: %s %s' % (request.method, request.path))  # 日志
        return await handler(request)  # 返回

    return logger_middleware


async def auth_factory(app, handler):
    async def auth(request):
        logging.info('check user: %s %s' % (request.method, request.path))
        request.__user__ = None  # 初始化
        cookie_str = request.cookies.get(COOKIE_NAME)  # 读取cookie
        if cookie_str:
            user = await cookie2user(cookie_str)
            if user:
                logging.info('set current user: %s' % user.email)
                request.__user__ = user
        if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
            return web.HTTPFound('/signin')
        return await handler(request)

    return auth


# 函数返回值转化为`web.response`对象
async def response_factory(app, handler):
    async def response_middleware(request):
        logging.info('Response handler...')
        r = await handler(request)
        #print(r, handler)
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r, bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r, str):
            if r.startswith('redirect:'):  # 重定向
                return web.HTTPFound(r[9:])  # 转入别的网站
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html;charset=utf-8'
            return resp
        if isinstance(r, dict):
            template = r.get('__template__')
            if template is None:  # 序列化JSON那章，传递数据
                resp = web.Response(body=json.dumps(r, ensure_ascii=False, default=lambda o: o.__dict__).encode(
                    'utf-8'))  # https://docs.python.org/2/library/json.html#basic-usage
                return resp
            else:  # jinja2模板
                r['user'] = request.__user__
                resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
                resp.content_type = 'text/html;charset=utf-8'
                return resp
        if isinstance(r, int) and r >= 100 and r < 600:
            return web.Response(r)
        if isinstance(r, tuple) and len(r) == 2:
            t, m = r
            if isinstance(t, int) and t >= 100 and t < 600:
                return web.Response(t, str(m))
        # default，错误
        resp = web.Response(body=str(r).encode('utf-8'))
        resp.content_type = 'text/plain;charset=utf-8'
        return resp

    return response_middleware
