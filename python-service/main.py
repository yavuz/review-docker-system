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

        # Mağazanın import durumunu "product_info_being_fetched" olarak güncelle
        stores_collection = directus.collection('stores')
        await stores_collection.update(store_data['id'], {
            'import_status': 'fetching_store_reviews'
        })

        # Dynamically import the appropriate parser module
        parser_module = importlib.import_module(f'parsers.{store_type}')
        
        # Call the parse_store function from the parser module to get products
        products = await parser_module.parse_store(store_data)
        
        if products and isinstance(products, list):
            print(f"Adding {len(products)} products to Directus...")
            
            processed_products = []
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
                        product['user'] = store_data.get('user')  # Add user data from store
                        updated_product = await products_collection.update(existing_product.items[0]['id'], product)
                        processed_products.append(updated_product)
                        print(f"Updated product: {product['name']}")
                    else:
                        # Ürün yoksa yeni ekle
                        product['user'] = store_data.get('user')  # Add user data from store
                        created_product = await products_collection.create(product)
                        processed_products.append(created_product)
                        print(f"Added new product: {product['name']}")
                except Exception as e:
                    print(f"Error processing product {product['name']}: {str(e)}")
                    continue
            
            # Mağazanın import durumunu güncelle
            await stores_collection.update(store_data['id'], {
                'import_status': 'product_info_fetched'
            })


            print("Fetching reviews...")
            try:
                # Yorumları çekmek için parse_store_reviews fonksiyonunu çağır
                reviews_module = importlib.import_module(f'parsers.{store_type}')

                print(f"Processing reviews for {store_data['name']}")

                # Önce yorumları çekelim
                raw_reviews = reviews_module.fetch_all_store_reviews(
                    store_data['api_connect_info']['store_id'],
                    store_data['api_connect_info']['token_key']
                )

                # Her bir yorum için products tablosundan ID'yi bulalım
                reviews_collection = directus.collection('reviews')
                products_collection = directus.collection('products')

                for review in raw_reviews:
                    try:
                        # review_target_id'yi oluştur
                        review_target_id = f"{store_type}_{review['contentId']}"
                        
                        # Önce bu review'in daha önce eklenip eklenmediğini kontrol et
                        existing_review = await reviews_collection.filter(
                            F(review_target_id=review_target_id)
                        ).read()

                        # Products tablosundan eşleşen ürünü bul
                        matching_product = await products_collection.filter(
                            (F(store_type=store_type) & F(product_id=str(review['contentId'])))
                        ).read()

                        if matching_product.items:
                            product_id = matching_product.items[0]['id']
                            
                            # Review nesnesini hazırla
                            content = review.get('comment', '')
                            rating = review.get('rate', 0)
                            review_date = datetime.fromtimestamp(review['createdDate'] / 1000.0).strftime('%Y-%m-%d')
                            review_created_date = datetime.fromtimestamp(review['createdDate'] / 1000.0).isoformat()
                            
                            # Sentiment hesaplama
                            if rating >= 4:
                                sentiment = 'positive'
                            elif rating == 3:
                                sentiment = 'neutral'
                            else:
                                sentiment = 'negative'

                            review_data = {
                                "review_target_id": review_target_id,
                                "product": product_id,
                                "content": content,
                                "rating": rating,
                                "review_date": review_date,
                                "review_created_date": review_created_date,
                                "source": "Trendyol",
                                "sentiment": sentiment,
                                "status": "published",
                                "store": store_data['id'],
                                "extra_fields": review,
                                "user": store_data.get('user')  # Add user data from store
                            }

                            if existing_review.items:
                                # Review varsa güncelle
                                await reviews_collection.update(existing_review.items[0]['id'], review_data)
                                print(f"Updated review: {review_target_id}")
                            else:
                                # Review yoksa yeni ekle
                                await reviews_collection.create(review_data)
                                print(f"Added new review: {review_target_id}")
                        else:
                            print(f"Warning: No matching product found for {review_target_id}")

                    except Exception as e:
                        print(f"Error processing review {review_target_id}: {str(e)}")
                        continue

                # Mağazanın review import durumunu güncelle
                await stores_collection.update(store_data['id'], {
                    'import_status': 'reviews_fetched'
                })

            except Exception as e:
                print(f"Error fetching reviews: {str(e)}")
            
            return True
        return False
    except ImportError:
        print(f"No parser found for store type: {store_type}")
        return False
    except Exception as e:
        # Ürün çekme sırasında hata olursa
        await stores_collection.update(store_data['id'], {
            'import_status': 'error_while_fetching_product_info'
        })
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
            .filter(F(id='73')) \
            .limit(10) \
            .read()
    
        #.filter(F(import_status='store_reviews_fetched')) \

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
