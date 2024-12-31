import requests
import os
from datetime import datetime
from typing import List, Dict, Any
from py_directus import Directus, F
from subscription_manager import initialize_subscription_limits, update_subscription_usage, SubscriptionLimits
import json

# Global variables
STORE_TYPE = 'trendyol'

def fetch_store_data(store_id: str, token_key: str, page: int = 0, approved: bool = True, size: int = 50) -> dict:
    """
    Fetch store data from Trendyol API
    
    Args:
        store_id (str): Store ID for Trendyol
        token_key (str): Authorization token key
        page (int): Page number for pagination
        approved (bool): Filter for approved products
        size (int): Number of items per page
        
    Returns:
        dict: API response data
    """
    url = f'https://api.trendyol.com/sapigw/suppliers/{store_id}/products'
    
    headers = {
        'Authorization': f'Basic {token_key}',
        'User-Agent': f'{store_id} - Trendyolsoft'
    }
    
    params = {
        'page': page,
        'approved': str(approved),
        'size': size
    }
    
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    
    return response.json()

def fetch_all_store_data(store_id: str, token_key: str, approved: bool = True, size: int = 50) -> list:
    """
    Fetch all pages of store data from Trendyol API
    
    Args:
        store_id (str): Store ID for Trendyol
        token_key (str): Authorization token key
        approved (bool): Filter for approved products
        size (int): Number of items per page
        
    Returns:
        list: All products from all pages
    """
    all_products = []
    current_page = 0
    
    while True:
        response = fetch_store_data(store_id, token_key, current_page, approved, size)
        #print("API Yanıt Yapısı:", json.dumps(response, indent=2, ensure_ascii=False))
        
        if 'content' not in response:
            print("Uyarı: API yanıtında 'content' anahtarı bulunamadı")
            print("Tam API yanıtı:", response)
            break
            
        all_products.extend(response['content'])
        
        if current_page >= response['totalPages'] - 1:
            break
            
        current_page += 1
    
    return all_products

def transform_product_for_directus(product: dict, directus_store_id: str) -> dict:
    """
    Trendyol ürün verisini Directus formatına dönüştürür.
    """
    # Gelen veriyi kontrol etmek için
    #print("Ürün Anahtarları:", product.keys())
    #print("Ürün Verisi:", json.dumps(product, indent=2, ensure_ascii=False))

    try:
        # Ana alanları eşleştir
        directus_product = {
            "product_id": str(product.get('productContentId', '')),
            "sku": str(product.get("stockCode", '')),
            "name": product.get("title", ''),
            "description": product.get("description", ''),
            "price": float(product.get("salePrice", 0)),
            "category": product.get("categoryName", ''),
            "status": "published" if product.get("approved", False) and not product.get("archived", True) else "draft",
            "sort": None,
            "store": directus_store_id,
            "url": product.get("productUrl", ''),
            "images": [img.get("url", '') for img in product.get("images", [])],
            "store_type": "trendyol",
            "extra_fields": {}
        }
        
        # Kalan tüm alanları extra_fields'e ekle
        for key, value in product.items():
            if key not in ["productCode", "stockCode", "title", "description", "salePrice", 
                          "categoryName", "approved", "archived", "productUrl", "images"]:
                directus_product["extra_fields"][key] = value
                
        return directus_product
        
    except Exception as e:
        print(f"Ürün dönüştürme hatası: {str(e)}")
        print(f"Sorunlu ürün verisi: {product}")
        raise e

async def parse_store(store_data):
    print(f"Processing Trendyol store: {store_data['name']}")
    api_info = store_data.get('api_connect_info', {})
    
    # user_id'yi store_data'dan al
    user_id = store_data.get('user')
    if not user_id:
        print("User ID bulunamadı")
        return False
        
    store_data['user_id'] = user_id

    if api_info:
        try:
            print(f"Processing with API credentials: {api_info['store_id']}")
            
            # Başlangıçta limitleri al
            directus = await Directus(os.getenv("DIRECTUS_API_URL"), token=os.getenv("DIRECTUS_API_TOKEN"))
            subscription_limits, package_info = await initialize_subscription_limits(directus, user_id)

            print(f"Subscription limits: {subscription_limits.product_limit} products, {subscription_limits.review_limit} reviews")
            
            
            if not package_info:
                print("Paket bilgisi bulunamadı")
                return False

            # Ürünleri çek
            all_products = fetch_all_store_data(
                store_id=api_info['store_id'],
                token_key=api_info['token_key'],
            )

            print(f"Total products fetched: {len(all_products)}")
            
            
            # Ürünleri Directus formatına dönüştür
            directus_products = [
                transform_product_for_directus(product, store_data['id']) 
                for product in all_products
            ]

            #print("Tüm Ürünler:", directus_products)
            print(f"Total products transformed: {len(directus_products)}")
            
            
            # Ürünleri Directus'a ekle
            processed_products = await add_products_to_directus(directus_products, store_data, subscription_limits)
            print(f"Total products processed: {len(processed_products)}")

            # Yorumları çek ve ekle
            raw_reviews = fetch_all_store_reviews(
                store_id=api_info['store_id'],
                token_key=api_info['token_key']
            )
            print(f"Total reviews fetched: {len(raw_reviews)}")
            
            # Yorumları Directus'a ekle
            await add_reviews_to_directus(raw_reviews, store_data, subscription_limits)
            
            # İşlem sonunda kullanım istatistiklerini güncelle
            await update_subscription_usage(directus, user_id, subscription_limits)
            
            return processed_products

        except Exception as e:
            print(f"Error in parse_store: {str(e)}")
            return []

    return True

def fetch_store_reviews(store_id: str, token_key: str, page: int = 0, size: int = 1000) -> Dict[str, Any]:
    """
    Fetch product reviews for a specific store from Trendyol API
    
    Args:
        store_id (str): Store ID for Trendyol
        token_key (str): Authorization token key
        page (int): Page number for pagination
        size (int): Number of items per page
        
    Returns:
        dict: API response data with reviews
    """
    #url = f'https://public.trendyol.com/discovery-sellerstore-webgw-service/v1/ugc/product-reviews/reviews/{store_id}'
    url = f'https://yavuzyildirim.com/test.json'
    
    headers = {
        'User-Agent': f'{store_id} - Trendyolsoft'
    }
    
    params = {
        'page': page,
        'size': size,
        'isMarketplaceMember': 'true'
    }
    
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    
    return response.json()

def fetch_all_store_reviews(store_id: str, token_key: str, size: int = 1000) -> List[Dict[str, Any]]:
    """
    Fetch all pages of store reviews from Trendyol API
    
    Args:
        store_id (str): Store ID for Trendyol
        token_key (str): Authorization token key
        size (int): Number of items per page
        
    Returns:
        list: All reviews from all pages
    """
    all_reviews = []
    current_page = 0
    
    while True:
        response = fetch_store_reviews(store_id, token_key, current_page, size)
        
        # Extract reviews from nested structure
        reviews_data = response.get('productReviews', {})
        
        current_reviews = reviews_data.get('content', [])
        all_reviews.extend(current_reviews)

        print(f"Total reviews fetched: {len(all_reviews)}")
        
        total_pages = reviews_data.get('totalPages', 0)
        print(f"Total pages: {total_pages}")
        if current_page >= total_pages - 1:
            break
            
        current_page += 1
    
    return all_reviews

async def add_products_to_directus(products: List[Dict], store_data: Dict, subscription_limits: SubscriptionLimits):
    """
    Ürünleri Directus'a ekler veya günceller
    """
    directus = await Directus(os.getenv("DIRECTUS_API_URL"), token=os.getenv("DIRECTUS_API_TOKEN"))
    
    processed_products = []

    print(f"Adding/Updating products in Directus: {len(products)}")
    
    for product in products:
        # Limit kontrolü
        if not subscription_limits.can_add_product():
            print(f"Ürün limiti aşıldı. Maksimum: {subscription_limits.product_limit}")
            break

        try:
            products_collection = directus.collection('products')

            # Ürünün zaten var olup olmadığını kontrol et
            existing_product = await products_collection.filter(
                (F(sku=product['sku']) & F(store=store_data['id']))
            ).read()
            
            # User bilgisini ekle
            product['user'] = store_data.get('user')
            
            if existing_product.items:
                # Ürün varsa güncelle
                updated_product = await products_collection.update(existing_product.items[0]['id'], product)
                processed_products.append(updated_product)
                subscription_limits.add_product()  # Sadece yeni eklenen ürünler için sayacı artır
                print(f"Updated product: {product['extra_fields']['productContentId']}")
            else:
                # Ürün yoksa ve limit uygunsa yeni ekle
                created_product = await products_collection.create(product)
                processed_products.append(created_product)
                subscription_limits.add_product()  # Sadece yeni eklenen ürünler için sayacı artır
                print(f"Added new product: {product['extra_fields']['productContentId']}")
                
        except Exception as e:
            print(f"Ürün işlenirken hata oluştu: {str(e)}")
            continue
    
    return processed_products

async def add_reviews_to_directus(raw_reviews: List[Dict], store_data: Dict, subscription_limits: SubscriptionLimits):
    """
    Yorumları Directus'a ekler
    """
    directus = await Directus(os.getenv("DIRECTUS_API_URL"), token=os.getenv("DIRECTUS_API_TOKEN"))
    
    reviews_collection = directus.collection('reviews')
    products_collection = directus.collection('products')
    store_type = STORE_TYPE
    
    for review in raw_reviews:
        try:
            print("***********************************")
            print(subscription_limits.can_add_review())
            # Limit kontrolü
            if not subscription_limits.can_add_review():
                print(f"Yorum limiti aşıldı. Maksimum: {subscription_limits.review_limit}")
                break

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
                    "source": STORE_TYPE,
                    "sentiment": sentiment,
                    "status": "published",
                    "store_id": store_data['id'],
                    "extra_fields": review,
                    "user": store_data.get('user')
                }
                
                if existing_review.items:
                    # Review varsa güncelle
                    await reviews_collection.update(existing_review.items[0]['id'], review_data)
                    subscription_limits.add_review()
                    print(f"Updated review: {review_target_id}")
                else:
                    # Review yoksa yeni ekle
                    await reviews_collection.create(review_data)
                    print(f"Added new review: {review_target_id}")
                    subscription_limits.add_review()
            else:
                print(f"Warning: No matching product found for {review_target_id}")
                
        except Exception as e:
            print(f"Error processing review: {str(e)}")
            continue