import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def check_db():
    import certifi
    uri = "mongodb+srv://<username>:<password>@<cluster-host>/<database>?retryWrites=true&w=majority"
    client = AsyncIOMotorClient(uri, tls=True, tlsCAFile=certifi.where())
    db = client.get_default_database()
    
    print("--- Documents ---")
    async for doc in db.documents.find():
        print(f"ID: {doc['_id']}, CompanyId: {doc.get('companyId')}, Filename: {doc.get('filename')}, Status: {doc.get('status')}, Error: {doc.get('error')}")
        
    print("\n--- All Users ---")
    async for user in db.users.find():
        print(f"ID: {user['_id']}, Email: {user.get('email')}, Role: {user.get('role')}, Company: {user.get('companyId')}")

if __name__ == "__main__":
    asyncio.run(check_db())
