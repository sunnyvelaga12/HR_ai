import httpx
import asyncio

async def run():
    async with httpx.AsyncClient() as client:
        resp = await client.post('http://localhost:9000/api/auth/signup', json={
            'email': 'test2@test.com',
            'password': 'password123',
            'role': 'hr_admin',
            'companyName': 'Test Corp'
        })
        print(resp.status_code)
        print(resp.text)

asyncio.run(run())
