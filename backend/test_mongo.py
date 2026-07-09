import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def test():
    client = AsyncIOMotorClient(
        'mongodb+srv://<username>:<password>@<cluster-host>/<database>?retryWrites=true&w=majority',
        tls=True,
        tlsAllowInvalidCertificates=True,
        serverSelectionTimeoutMS=5000
    )
    try:
        res = await client.admin.command('ping')
        print('PING OK:', res)
    except Exception as e:
        print('ERROR:', e)

asyncio.run(test())
