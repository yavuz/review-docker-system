import os
import asyncio
from py_directus import Directus, F
from dotenv import load_dotenv
import pprint

# Load environment variables from .env file
load_dotenv()

async def fetch_store_data():
    directus_api_url = os.getenv("DIRECTUS_API_URL")
    directus_api_token = os.getenv("DIRECTUS_API_TOKEN")
    
    if not directus_api_url or not directus_api_token:
        print("Environment variables for Directus API URL or Token are not set.")
        return
    
    directus = await Directus(directus_api_url, token=directus_api_token)
    
    try:
        stores = await directus.collection('stores') \
            .filter(F(import_status='product_info_not_fetched')) \
            .limit(10) \
            .read()
        if stores.items:
            pprint.pprint(stores.items)
        else:
            print("No data found.")
    except Exception as e:
        print("Failed to fetch data:", str(e))

if __name__ == "__main__":
    asyncio.run(fetch_store_data())
