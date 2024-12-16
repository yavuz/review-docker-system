import os
import asyncio
import importlib
from datetime import datetime
from py_directus import Directus, F
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

async def process_store(store_data):
    store_type = store_data.get('store_type', '').lower()
    try:
        # Directus bağlantısını oluştur
        directus_api_url = os.getenv("DIRECTUS_API_URL")
        directus_api_token = os.getenv("DIRECTUS_API_TOKEN")
        directus = await Directus(directus_api_url, token=directus_api_token)

        # Mağazanın import durumunu "fetching_store_reviews" olarak güncelle
        stores_collection = directus.collection('stores')
        await stores_collection.update(store_data['id'], {
            'import_status': 'fetching_store_reviews'
        })

        # Dynamically import the appropriate parser module
        parser_module = importlib.import_module(f'parsers.{store_type}')
        
        print("Parser module: ", store_type)
        print("Store data: ", store_data)
        
        # Call the parse_store function from the parser module to get products
        await parser_module.parse_store(store_data)
        
        # Mağazanın import durumunu "completed" olarak güncelle
        await stores_collection.update(store_data['id'], {
            'import_status': 'store_reviews_fetched'
        })

    except Exception as e:
        print(f"Error in process_store: {str(e)}")
        # Hata durumunda import_status'u "error" olarak güncelle
        stores_collection = directus.collection('stores')
        await stores_collection.update(store_data['id'], {
            'import_status': 'error'
        })

async def fetch_store_data():
    try:
        # Directus bağlantısını oluştur
        directus_api_url = os.getenv("DIRECTUS_API_URL")
        directus_api_token = os.getenv("DIRECTUS_API_TOKEN")
        directus = await Directus(directus_api_url, token=directus_api_token)

        # Get stores collection
        # stores_collection = directus.collection('stores')

        stores_collection = directus.collection('stores') \
            .filter(F(import_status='product_info_not_fetched')) \
            .limit(10)

        #
        #.filter(F(id='73')) \

        print("Getting stores...")

        stores = await stores_collection.read()
        
        if not stores.items:
            print("Hiç mağaza bulunamadı.")
            return
        
        print(f"Toplam {len(stores.items)} mağaza bulundu.")

        # Process each store
        for store in stores.items:
            await process_store(store)

    except Exception as e:
        print(f"Error in fetch_store_data: {str(e)}")

if __name__ == "__main__":
    asyncio.run(fetch_store_data())
