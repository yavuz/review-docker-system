import requests
from datetime import datetime
from typing import List, Dict, Any

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
        all_products.extend(response['content'])
        
        if current_page >= response['totalPages'] - 1:
            break
            
        current_page += 1
    
    return all_products

def transform_product_for_directus(product: dict, directus_store_id: str) -> dict:
    """
    Trendyol ürün verisini Directus formatına dönüştürür.
    
    Args:
        product (dict): Trendyol'dan gelen ürün verisi
        directus_store_id (str): Directus'taki mağaza ID'si
        
    Returns:
        dict: Directus formatında ürün verisi
    """
    # Ana alanları eşleştir
    directus_product = {
        "product_id": str(product["productContentId"]),
        "sku": product["stockCode"],
        "name": product["title"],
        "description": product["description"],
        "price": product["salePrice"],
        "category": product["categoryName"],
        "status": "published" if product["approved"] and not product["archived"] else "draft",
        "sort": None,
        "store": directus_store_id,
        "url": product["productUrl"],
        "images": [img["url"] for img in product["images"]],
        "store_type": "trendyol",
        "extra_fields": {}
    }
    
    # Kalan tüm alanları extra_fields'e ekle
    for key, value in product.items():
        if key not in ["productCode", "stockCode", "title", "description", "salePrice", 
                      "categoryName", "approved", "archived", "productUrl", "images"]:
            directus_product["extra_fields"][key] = value
            
    return directus_product

async def parse_store(store_data):
    print(f"Processing Trendyol store: {store_data['name']}")
    api_info = store_data.get('api_connect_info', {})

    if api_info:
        print(f"Processing with API credentials: {api_info['store_id']}")

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

        # print(f"Total products transformed: {directus_products}")
        
        return directus_products

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