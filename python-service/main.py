import os
import asyncio
import importlib
from py_directus import Directus, F
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

async def process_store(store_data):
    store_type = store_data.get('store_type', '').lower()
    try:
        # Dynamically import the appropriate parser module
        parser_module = importlib.import_module(f'parsers.{store_type}')
        # Call the parse_store function from the parser module
        products = await parser_module.parse_store(store_data)
        
        if products and isinstance(products, list):
            print(f"Adding {len(products)} products to Directus...")
            
            # Directus bağlantısını oluştur
            directus_api_url = os.getenv("DIRECTUS_API_URL")
            directus_api_token = os.getenv("DIRECTUS_API_TOKEN")
            directus = await Directus(directus_api_url, token=directus_api_token)

            print(f"Adding {len(products)} products to Directus...")
            for product in products:
                try:
                    # Ürünleri Directus'a ekle
                    products_collection = directus.collection('products')

                    # Ürünün zaten var olup olmadığını kontrol et (store_id ve sku'ya göre)
                    existing_product = await products_collection.filter(
                        (F(sku=product['sku']) & F(store=store_data['id']))
                    ).read()
                    
                    if existing_product.items:
                        # Ürün varsa güncelle
                        await products_collection.update(existing_product.items[0]['id'], product)
                        print(f"Updated product: {product['name']}")
                    else:
                        # Ürün yoksa yeni ekle
                        await products_collection.create(product)
                        print(f"Added new product: {product['name']}")
                except Exception as e:
                    print(f"Error processing product {product['name']}: {str(e)}")
                    continue
            
            # Mağazanın import durumunu güncelle
            stores_collection = directus.collection('stores')
            await stores_collection.update(store_data['id'], {
                'import_status': 'product_info_fetched'
            })
            
            return True
        return False
    except ImportError:
        print(f"No parser found for store type: {store_type}")
        return False
    except Exception as e:
        print(f"Error processing store {store_data['name']}: {str(e)}")
        return False

async def fetch_store_data():
    print("Fetching store data...")
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
            for store in stores.items:
                directus_store_id = store['id']
                print(f"\nProcessing store: {store['name']}")
                await process_store(store)
        else:
            print("No data found.")
    except Exception as e:
        print("Failed to fetch data:", str(e))

if __name__ == "__main__":
    asyncio.run(fetch_store_data())
