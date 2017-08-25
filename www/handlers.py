import asyncio
from models import User, Comment, Blog
from coreweb import get, post
import time, hashlib, re, json
from config import configs
from apis import *
from models import next_id
from aiohttp import web
import logging
import markdown2

logging.basicConfig(level=logging.INFO)
COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs['session']['secret']
_RE_EMAIL = re.compile(r'^(\w)+(\.\w)*\@(\w)+((\.\w{2,3}){1,3})$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')


def text2html(text):
    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'),
                filter(lambda s: s.strip() != '', text.split('\n')))
    return ''.join(lines)


def user2cookie(user, max_age):
    expires = str(time.time() + max_age)
    s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)


async def cookie2user(cookie_str):
    if not cookie_str:
        return None
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
            return None
        uid, expires, sha1 = L
        if float(expires) < time.time():
            return None
        user = await User.find(uid)
        if not user:
            return None
        s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.passwd = "******"
        return user
    except Exception as e:
        logging.exception(e)
        return None

        # 检测有否登录且是否为管理员


def check_admin(request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()


# 编写用于测试的URL处理函数
# ***************************************************************************
'''
用户浏览页面包括：
注册页：GET /register
登录页：GET /signin
注销页：GET /signout
首页：GET /
日志详情页：GET /blog/:blog_id 
'''


@get('/')
async def index(request):
    summary = 'Hello,World.'
    blogs = await Blog.findAll(orderBy='created_at desc')
    ''' [
        Blog(id='1', name='Test Blog', summary=summary, create_at=time.time() - 120),
        Blog(id='2', name='Something New', summary=summary, create_at=time.time() - 3600),
        Blog(id='3', name='Learn Swift', summary=summary, create_at=time.time() - 7200)
    ]
    '''
    return {
        '__template__': 'blogs.html',
        'blogs': blogs,
        
    }


@get('/register')
def register():
    return {
        '__template__': 'register.html'
    }


@get('/signin')
def signin():
    return {
        '__template__': 'signin.html'
    }


@get('/signout')
def sigout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r


@get('/blog/{id}')
async def get_blog(id):
    blog = await Blog.find(id)
    comments = await Comment.findAll('blog_id=?', [id], orderBy='created_at desc')
    for c in comments:
        c.html_content = text2html(c.content)
    blog.html_content = markdown2.markdown(blog.content)
    return {
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments

    }


# ***************************************************************************
'''
管理页面包括：
评论列表页：GET /manage/comments
日志列表页：GET /manage/blogs
创建日志页：GET /manage/blogs/create
修改日志页：GET /manage/blogs/
用户列表页：GET /manage/users
'''


@get('/manage/')
def manage():
    return 'redirect:/manage/comments'


@get('/manage/comments')
def manage_comments(*, page='1'):
    return {
        '__template__': 'manage_comments.html',
        'page_index': Page.get_page_index(page)
    }


@get('/manage/blogs/create')
def manage_create_blog(request):
    return {

        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs',
        
    }


@get('/manage/blogs/edit')
def manage_edit_blog(*, id):
    return {
        '__template__': 'manage_blog_edit.html',
        'id': id,
        'action': '/api/blogs/%s' % id
    }


@get('/manage/users')
def manage_users(*, page='1'):
    return {
        '__template__': 'manage_users.html',
        'page_index': Page.get_page_index(page)
    }


@get('/manage/blogs')
def manage_blogs(request, *, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': Page.get_page_index(page),
        
    }


# ******************************************************************************
'''
后端API包括：

获取日志：GET /api/blogs
创建日志：POST /api/blogs
修改日志：POST /api/blogs/:blog_id
删除日志：POST /api/blogs/:blog_id/delete
获取评论：GET /api/comments
创建评论：POST /api/blogs/:blog_id/comments
删除评论：POST /api/comments/:comment_id/delete
创建新用户：POST /api/users
获取用户：GET /api/users
'''


@get('/api/blogs')
async def api_blogs(*, page='1'):
    page_index = Page.get_page_index(page)
    num = await Blog.findNumber('count(id)')
    p = Page(item_count=num, page_index=page_index)
    if num == 0:  # 数据库没日志
        return dict(page=p, blogs=())
    else:
        blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, blogs=blogs)


@get('/api/blogs/{id}')
async def api_get_blog(*, id):
    blog = await Blog.find(id)
    return blog


@post('/api/blogs/{id}')
async def api_update_blog(id, request, *, name, summary, content):
    check_admin(request)
    blog = await Blog.find(id)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog.name = name.strip()
    blog.summary = summary.strip()
    blog.content = content.strip()
    await blog.update()
    return blog


@post('/api/blogs/{id}/delete')
async def api_delete_blog(request, *, id):
    check_admin(request)
    blog = await Blog.find(id)
    await blog.remove()
    return dict(id=id)


@post('/api/blogs')
async def create_blogs(request, *, name, content, summary):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'name can not empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary can not empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content can not empty.')
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image,
                summary=summary.strip(), name=name.strip(), content=content.strip())
    await blog.save()
    return blog


@get('/api/comments')
async def api_comments(*, page='1'):
    page_index = Page.get_page_index(page)
    num = await Comment.findNumber('count(id)')
    p = Page(item_count=num, page_index=page_index)
    if num == 0:
        return dict(page=p, comments=())
    comments = await Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, comments=comments)


@post('/api/blogs/{id}/comments')
async def api_create_comment(id, request, *, content):
    user = request.__user__
    if user is None:
        raise APIPermissionError('Please signin first.')
    if not content or not content.strip():
        raise APIValueError('content')
    blog = await Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name, user_image=user.image,
                      content=content.strip())
    await comment.save()
    return comment


@post('/api/comments/{id}/delete')
async def api_delete_comments(id, request):
    check_admin(request)
    c = await Comment.find(id)
    if c is None:
        raise APIResourceNotFoundError('Comment')
    await c.remove()
    return dict(id=id)


@get('/api/users')
async def api_get_users(*, page='1'):
    page_index = Page.get_page_index(page)
    num = await User.findNumber('count(id)')
    p = Page(item_count=num, page_index=page_index)
    if num == 0:
        return dict(page=p, users=())
    users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    for u in users:
        u.passwd = '******'
    return dict(page=p, users=users)


@post('/api/users')
async def api_register_user(*, name, email, passwd):
    if not name or not name.strip():  # 如果名字是空格或没有返错，这里感觉not name可以省去，因为在web框架中的RequsetHandler已经验证过一遍了
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd and not _RE_SHA1.match(passwd):
        raise APIValueError('password')
    users = await User.findAll(where='email=?', args=[email])
    if len(users) > 0:
        raise APIError('register:failed', 'email', 'Email is already in use.')
    uid = next_id()
    sha1_passwd = '%s:%s' % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),
                image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    await user.save()
    # 制作cookie返回浏览器客户端
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'  # 掩盖passwd
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


@post('/api/authenticate')
async def authenticate(*, email, passwd):
    if not email or not email.strip():
        raise APIValueError('email')
    if not passwd or not passwd.strip():
        raise APIValueError('passwd')
    users = await User.findAll(where='email=?', args=[email])
    if len(users) == 0:
        raise APIValueError('email', 'Email not exist.')
    user = users[0]
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(':'.encode('utf-8'))
    sha1.update(passwd.encode('utf-8'))
    if sha1.hexdigest() != user.passwd:
        raise APIValueError('password', 'Invaild password')
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = "******"
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r
