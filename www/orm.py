# -*- coding: utf-8 -*-
import asyncio, logging

import aiomysql

logging.basicConfig(level=logging.INFO)
log_file = "./basic_logger.log"

logging.basicConfig(filename=log_file, level=logging.INFO)


def log(sql, args=()):
    logging.info('SQL: %s' % sql)


async def create_pool(loop, **kw):
    logging.info('create database connection pool')
    global __pool
    __pool = await aiomysql.create_pool(
        host=kw.get('host', 'localhost'),
        port=kw.get('port', 3306),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
        loop=loop
    )


'''#    with (await __pool) as conn:
   #     cur = await conn.cursor()
   #     await cur.execute("show tables")
   #     print(cur.description)
   #     r = await cur.fetchall()
   #     print('*****',r,'*****')
   # __pool.close()
   # await __pool.wait_closed()

#loop = asyncio.get_event_loop()
#a=create_pool(loop,user='lrnsql',password='950314',db='bank')
#loop.run_until_complete(a)
'''


async def select(sql, args, size=None):
    # print('sql:', sql, args)
    log(sql, args)
    global __pool
    with (await __pool) as conn:
        cur = await conn.cursor(aiomysql.DictCursor)  # 创建游标,aiomysql.DictCursor的作用使生成结果是一个dict
        await cur.execute(sql.replace('?', '%s'), args or ())
        if size:
            rs = await cur.fetchmany(size)
        else:
            rs = await cur.fetchall()
        await cur.close()
        logging.info('rows returned : %s' % len(rs))
        return rs


async def execute(sql, args):
    log(sql)
    # print('sql:', sql, args)
    with (await __pool) as conn:
        try:
            cur = await conn.cursor()
            await cur.execute(sql.replace('?', '%s'), args)
            affected = cur.rowcount
            await cur.close()
        except BaseException as e:
            raise
        return affected


def create_args_string(num):
    lol = []
    for n in range(num):
        lol.append('?')
    return (','.join(lol))


class Field(object):
    def __init__(self, name, colum_type, primary_key, default):
        self.name = name
        self.colum_type = colum_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self):
        return '%s,%s:%s' % (self.__class__.__name__, self.colum_type, self.name)


class StringField(Field):
    def __init__(self, name=None, ddl='varchar(100)', primary_key=False, default=None):
        super(StringField, self).__init__(name, ddl, primary_key, default)


class BooleanField(Field):
    def __init__(self, name=None, ddl='boolean', primary_key=False, default=False):
        super(BooleanField, self).__init__(name, ddl, primary_key, default)


class IntegerField(Field):
    def __init__(self, name=None, ddl='bigint', primary_key=False, default=0):
        super(IntegerField, self).__init__(name, ddl, primary_key, default)


class FloatField(Field):
    def __init__(self, name=None, ddl='real', primary_key=False, default=0.0):
        super(FloatField, self).__init__(name, ddl, primary_key, default)


class TextField(Field):
    def __init__(self, name=None, ddl='Text', primary_key=False, default=None):
        super(TextField, self).__init__(name, ddl, primary_key, default)


class ModelMetaclass(type):
    def __new__(cls, name, bases, attrs):
        if name == 'Model':
            return type.__new__(cls, name, bases, attrs)
        table_name = attrs.get('__table__', None) or name
        logging.info('Found table:%s (table : %s)' % (name, table_name))
        mappings = dict()
        fields = []
        primaryKey = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('Found mapping:%s ==> %s' % (k, v))
                mappings[k] = v
                if v.primary_key:
                    logging.info('fond primary key hahaha %s' % k)
                    if primaryKey:
                        raise RuntimeError('Duplicated key for field')
                    primaryKey = k
                else:
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError('Primary key not found!')
            # w下面位字段从类属性中删除Field 属性
        for k in mappings.keys():
            attrs.pop(k)
        escaped_fields = list(map(lambda f: '`%s`' % f, fields))
        # 保存属性和列的映射关系
        attrs['__mappings__'] = mappings
        # 保存表名
        attrs['__table__'] = table_name
        # 保存主键名称
        attrs['__primary_key__'] = primaryKey
        # 保存主键外的属性名
        attrs['__fields__'] = fields
        attrs['__select__'] = 'select `%s` ,%s from `%s`' % (primaryKey, ','.join(escaped_fields), table_name)
        attrs['__insert__'] = 'insert into `%s` (%s,`%s`) values (%s) ' % (
            table_name, ','.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s` = ?' % (
            table_name, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (table_name, primaryKey)
        return type.__new__(cls, name, bases, attrs)


class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kw):
        super(Model, self).__init__(**kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError("'Model' object have no attribution: %s" % key)

    def __setattr__(self, key, value):
        self[key] = value

    def getValue(self, key):
        return getattr(self, key, None)

    def getValueOrDefault(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self, key, value)
        return value

    @classmethod
    async def findAll(cls, where=None, args=None, **kw):
        sql = [cls.__select__]
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []

        orderBy = kw.get('orderBy', None)
        if orderBy:
            sql.append('order by')
            sql.append(orderBy)
        limit = kw.get('limit', None)
        if limit is not None:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?,?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value : %s ' % str(limit))

        rs = await select(' '.join(sql), args)
        return [cls(**r) for r in rs]

    @classmethod
    async def findNumber(cls, selectField, where=None, args=None):
        sql = ['select %s __num__ from `%s`' % (selectField, cls.__table__)]
        if where:
            sql.append('where')
            sql.append(where)
        rs = await select(' '.join(sql), args, 1)
        if len(rs) == 0:
            return None
        return rs[0]['__num__']

    @classmethod
    async def find(cls, primarykey):
        '''find object by primary key'''
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [primarykey], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    ''' @classmethod
    async  def findAll(cls, **kw):
        rs = []
        if len(kw) == 0:
            rs = await select(cls.__select__, None)
        else:
            args = []
            values = []
            for k, v in kw.items():
                args.append('%s=?' % k)
                values.append(v)
            rs = await select('%s where %s ' % (cls.__select__, ' and '.join(args)), values)
        return rs
    '''

    async def save(self):
        #  print(self.getValueOrDefault(self.__primary_key__))
        args = list(map(self.getValueOrDefault, self.__fields__))

        # print('save:%s' % args)
        args.append(self.getValueOrDefault(self.__primary_key__))
        #  print(self.__insert__,args)
        rows = await execute(self.__insert__, args)
        if rows != 1:
            #        print(self.__insert__)
            logging.warning('failed to insert record: affected rows: %s' % rows)

    async def update(self):
        args = list(map(self.getValue, self.__fields__))
        args.append(self.getValue(self.__primary_key__))
        rows = await execute(self.__update__, args)
        if rows != 1:
            logging.warning('failed to update record: affected rows: %s' % rows)

    async def remove(self):
        args = [self.getValue(self.__primary_key__)]
        # print('sql',self.__update__)
        rows = await execute(self.__delete__, args)
        if rows != 1:
            logging.warning('failed to remove by primary key: affected rows: %s' % rows)


'''
#if __name__ == "__main__":
class User(Model):
    __table__ = 'users'
    id = IntegerField(name='id', primary_key=True)
    name = StringField(name='username')
    email = StringField(name='email')
    password = StringField(name='password')


    # 创建异步事件的句柄
loop = asyncio.get_event_loop()


    # 创建实例
    
async def test():
    await create_pool(loop=loop, host='localhost', user='lrnsql', password='950314', db='bank')
    user1 = User(id=7, name='sly', email='111@gmail.com', password='fuckblog')
    user2 = User(id=9, name='sly', email='222@gmail.com', password='fuckblog')
    #print('user:',user.find('8'),'****','User:',User.find)
  #  await user1.remove()
   # await user2.remove()
    
    await user1.save()
    await User.findNumber()
   # await user2.save()
    await user1.update()
    r = await User.find(primarykey='11')
    print('r:',r)
    r = await User.findAll()
    print(1, r)
    r = await User.findAll(id='12')
    print(2, r)
    

u=test()
loop.run_until_complete(u)
#loop.close()'''
