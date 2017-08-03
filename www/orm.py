# -*- coding: utf-8 -*-
import asyncio,logging

import aiomysql

def log(sql,args=()):
    logging.info('SQL: %s' %sql)

async def create_pool(loop,**kw):
    logging.info('create database connection pool')
    global __pool
    __pool = await aiomysql.create_pool(
        host = kw.get('host','localhost'),
        port = kw.get('port',3306),
        user = kw['user'],
        password = kw['password'],
        db = kw['db'],
        charset = kw.get('charset','utf8'),
        autocommit = kw.get('autocommit',True),
        maxsize = kw.get('maxsize',10),
        minsize = kw.get('minsize',1),
        loop = loop
    )
    with (await __pool) as conn:
        cur = await conn.cursor()
        await cur.execute("show tables")
        print(cur.description)
        r = await cur.fetchall()
        print('*****',r,'*****')
    __pool.close()
    await __pool.wait_closed()


loop = asyncio.get_event_loop()
a=create_pool(loop,user='lrnsql',password='950314',db='bank')


loop.run_until_complete(a)