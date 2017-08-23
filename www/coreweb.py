import asyncio, os, inspect, logging, functools
from apis import APIError
from urllib import parse
from aiohttp import web


def HanderDecorator(path, *, method):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kw):
            return func(*args, **kw)

        wrapper.__route__ = path
        wrapper.__method__ = method
        # logging.info('%s',path)
        return wrapper

    return decorator


get = functools.partial(HanderDecorator, method='GET')
post = functools.partial(HanderDecorator, method='POST')


def get_required_kw_args(fn):  # 获取命名关键字参数
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if str(param.kind) == 'KEYWORD_ONLY' and param.default == inspect.Parameter.empty:
            args.append(name)
    return tuple(args)


def get_named_kw_args(fn):
    args = []
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if str(param.kind) == 'KEYWORD_ONLY':
            args.append(name)
    return tuple(args)


def has_named_kw_arg(fn):  # 判断有没有命名关键字参数
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if str(param.kind) == 'KEYWORD_ONLY':
            return True


def has_var_kw_arg(fn):  # 判断有没有关键字参数
    params = inspect.signature(fn).parameters
    for name, param in params.items():
        if str(param.kind) == 'VAR_KEYWORD':
            return True


def has_request_arg(fn):
    sig = inspect.signature(fn)
    params = sig.parameters
    found = False
    for name, param in params.items():
        if name == 'request':
            found = True
            continue
        if found and str(param.kind) != 'VAR_POSITIONAL' and str(param.kind) != 'KEYWORD_ONLY' and str(
                        param.kind != 'VAR_KEYWORD'):
            raise ValueError(
                'request parameter must be the last named parameter in function: %s%s' % (fn.__name__, str(sig)))
    return found


# 定义RequestHandler,正式向request参数获取URL处理函数所需的参数
class RequestHandler(object):
    def __init__(self, app, fn):
        self._app = app
        self._fn = fn
        self._required_kw_args = get_required_kw_args(fn)
        self._named_kw_args = get_named_kw_args(fn)
        self._has_named_kw_arg = has_named_kw_arg(fn)
        self._has_var_kw_arg = has_var_kw_arg(fn)
        self._has_request_arg = has_request_arg(fn)
        # logging.info('self._required_kw_args:%s,self._named_kw_args:%s'%(self._required_kw_args,self._named_kw_args))

    async def __call__(self, request):
        kw = None

        if self._has_named_kw_arg or self._has_var_kw_arg:

            if request.method == 'POST':
                if not request.content_type:
                    return web.HTTPBadRequest(text="Missing Content_Type")
                ct = request.content_type.lower()
                if ct.startswith('application/json'):
                    params = await request.json()
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest(text='JSON body must be object.')
                    kw = params
                elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
                    params = await request.post()
                    kw = dict(**params)
                else:
                    return web.HTTPBadRequest('text=Unsupported Content_Tpye: %s' % (request.content_type))
            if request.method == 'GET':
                qs = request.query_string
                if qs:
                    kw = dict()
                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
            logging.info('kw:%s' % kw)
        if kw is None:
            # a=request.match_info
            # logging.info('request.match_info :%s' % request.match_info)
            # logging.info('request.content_type :%s' % request.content_type.lower())
            kw = dict(**request.match_info)
            # logging.info('kw :%s' % kw)
        else:
            if not self._has_var_kw_arg and self._named_kw_args:  # 当函数参数没有关键字参数时，移去request除命名关键字参数所有的参数信息
                copy = dict()
                #   a=self._named_kw_args
                #      print(a(0))
                for tmp in self._named_kw_args:
                    #    print(type(tmp.name))

                    if tmp in kw:
                        copy[tmp] = kw[tmp]
                kw = copy
            for k, v in request.match_info.items():  # 检查命名关键参数
                if k in kw:
                    logging.warning('Duplicate arg name in named arg and kw args: %s' % k)
                kw[k] = v

        if self._has_request_arg:
            kw['request'] = request
            #  logging.info('kw:%s '% kw )
            #   logging.info('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
        if self._required_kw_args:  # 假如命名关键字参数(没有附加默认值)，request没有提供相应的数值，报错
            for name in self._required_kw_args:
                if name not in kw:
                    return web.HTTPBadRequest(text='Missing argument: %s' % name)
            logging.info('call with args: %s' % str(kw))

        try:
            r = await self._fn(**kw)
            return r
        except APIError as e:  # APIError另外创建
            return dict(error=e.error, data=e.data, message=e.message)


def add_route(app, fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    logging.info('********************method:%s,path:%s' % (method, path))
    if method is None or path is None:
        return ValueError('@get or @post not defined in %s.' % str(fn))
    if not asyncio.iscoroutine(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
        #   logging.info('********************%s' % fn)
    logging.info(
        'add route %s %s => %s(%s)' % (method, path, fn.__name__, ','.join(inspect.signature(fn).parameters.keys())))
    a = RequestHandler(app, fn)
    # logging.info(a)
    app.router.add_route(method, path, a)


def add_routes(app, module_name):
    n = module_name.rfind('.')
    if n == -1:
        mod = __import__(module_name, globals(), locals())
    else:
        name = module_name[n + 1:]
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    for attr in dir(mod):
        if attr.startswith('_'):
            continue
        fn = getattr(mod, attr)
        #  logging.info('fn name:%s'% fn)
        if callable(fn):
            method = getattr(fn, '__method__', None)
            path = getattr(fn, '__route__', None)
            if path and method:  # 这里要查询path以及method是否存在而不是等待add_route函数查询，因为那里错误就要报错了
                #  logging.info('aaa')
                add_route(app, fn)


def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)  # prefix (str) – URL path prefix for handled static files
    logging.info('add static %s => %s' % ('/static/', path))
