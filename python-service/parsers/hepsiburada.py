import json
import aiohttp
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
import asyncio
from datetime import datetime
import os
from py_directus import Directus, F

# Global variables
STORE_TYPE = 'hepsiburada'

async def parse_store(store_data: Dict) -> bool:
    try:
        print(f"Hepsiburada mağazası işleniyor: {store_data['name']}")
        api_info = store_data.get('api_connect_info', {})
        
        if not api_info:
            # API bilgisi yoksa durumu güncelle
            await update_import_status(store_data['id'], 'api_info_missing')
            return False
            
        directus_store_id = store_data.get('id')
        store_url = api_info['store_url']
        
        print("Store URL: ", store_url)
        print("Directus store ID: ", directus_store_id)
        
        # Mağaza bilgilerini çek
        store_details = await get_store_details(store_url)
        print("Store details: ", store_details)
        if store_details:
            await update_store_info(directus_store_id, store_details)
        else:
            # Mağaza detayları alınamazsa durumu güncelle
            await update_import_status(store_data['id'], 'store_details_fetch_failed')
            return False
        
        # Ürünleri çek
        products_result = await fetch_all_products(store_url, directus_store_id, store_data)
        if not products_result:
            # Ürünler çekilemezse durumu güncelle
            await update_import_status(store_data['id'], 'error_while_fetching_product_info')
            return False
        
        # Başarılı durumda import_status'u güncelle
        await update_import_status(store_data['id'], 'store_reviews_fetched')
        return True
        
    except Exception as e:
        print(f"Hata oluştu: {str(e)}")
        # Genel hata durumunda import_status'u güncelle
        await update_import_status(store_data['id'], 'error')
        return False

async def get_store_details(store_url: str) -> Optional[Dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0",
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'tr,en-US;q=0.7,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(store_url, headers=headers) as response:
                html = await response.text()
                
        soup = BeautifulSoup(html, 'html.parser')
        redux_store = soup.find('script', {'id': 'reduxStore'})
        
        if not redux_store:
            return None
            
        store_data = json.loads(redux_store.string)
        merchant_detail = store_data['merchantState']['merchantDetail']
        
        return {
            'name': merchant_detail['name'],
            'brand_name': merchant_detail['brandName'],
            'legal_name': merchant_detail['legalName'],
            'phone': merchant_detail['phoneNumber'],
            'kep': merchant_detail['kep'],
            'mersis_no': merchant_detail['mersisNumber'],
            'city': merchant_detail['city'],
            'rating': merchant_detail['ratingSummary']['lifetimeRating'],
            'rating_count': merchant_detail['ratingSummary']['ratingQuantity'],
            'tags': merchant_detail['tagList']
        }
    except Exception as e:
        print(f"Mağaza detayları alınırken hata: {str(e)}")
        return None

async def update_store_info(store_id: str, store_details: Dict) -> None:
    try:
        directus_api_url = os.getenv("DIRECTUS_API_URL")
        directus_api_token = os.getenv("DIRECTUS_API_TOKEN")
        directus = await Directus(directus_api_url, token=directus_api_token)
        
        stores_collection = directus.collection('stores')
        
        # Mağaza bilgilerini güncelle
        store_data = {
            'extra_fields': {
                'hepsiburada_details': store_details,
                'last_updated': datetime.now().isoformat()
            }
        }
        
        updated_store = await stores_collection.update(store_id, store_data)
        print(f"Mağaza bilgileri güncellendi: {store_id}")
        
    except Exception as e:
        print(f"Mağaza bilgileri güncellenirken hata: {str(e)}")

async def fetch_all_products(store_url: str, store_id: str, store_data: Dict) -> bool:
    try:
        page = 1
        total_products = None
        processed_products = 0
        
        # İlk sayfadan toplam ürün sayısını al
        first_page = await fetch_page_products(store_url, page)
        if first_page and 'totalProductCount' in first_page:
            total_products = first_page['totalProductCount']
            products = first_page['products']
        else:
            print("Ürün bilgisi alınamadı")
            return False

        print(f"Toplam ürün sayısı: {total_products}")

        while True:
            if not products:
                print(f"Sayfa {page} için ürün bulunamadı")
                break
            
            for product in products:
                await save_product(product, store_id, store_data)
                processed_products += 1
            
            if processed_products >= total_products:
                print(f"Tüm ürünler işlendi. Toplam: {processed_products}")
                break
            
            page += 1
            page_data = await fetch_page_products(store_url, page)
            if not page_data:
                break
            products = page_data['products']
            
            # Her 10 ürün işlendikten sonra kısa bir bekleme
            if processed_products % 10 == 0:
                await asyncio.sleep(1)

        return True
    except Exception as e:
        print(f"Ürünler işlenirken hata: {str(e)}")
        return False

async def fetch_page_products(store_url: str, page: int) -> Optional[Dict]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0",
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'tr,en-US;q=0.7,en;q=0.3',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    # URL'ye tab=allproducts ve sayfa parametresini ekle
    if '?' in store_url:
        base_url = f"{store_url}&tab=allproducts&sayfa={page}"
    else:
        base_url = f"{store_url}?tab=allproducts&sayfa={page}"
    
    print(f"Sayfa {page} yükleniyor: {base_url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, headers=headers) as response:
                if response.status != 200:
                    print(f"Hata: HTTP {response.status}")
                    return None
                    
                html = await response.text()
                
        soup = BeautifulSoup(html, 'html.parser')
        redux_store = soup.find('script', {'id': 'reduxStore'})
        
        if not redux_store:
            print("Redux store bulunamadı")
            return None
            
        store_data = json.loads(redux_store.string)
        merchant_search = store_data['merchantState']['merchantSearch']
        
        return {
            'totalProductCount': merchant_search['totalProductCount'],
            'products': merchant_search['products']
        }
    except Exception as e:
        print(f"Sayfa ürünleri alınırken hata: {str(e)}")
        return None

async def save_product(product: Dict, store_id: str, store_data: Dict) -> None:
    try:
        directus_api_url = os.getenv("DIRECTUS_API_URL")
        directus_api_token = os.getenv("DIRECTUS_API_TOKEN")
        directus = await Directus(directus_api_url, token=directus_api_token)
        
        products_collection = directus.collection('products')
        
        product_data = {
            'product_id': product['productId'],
            'sku': product['sku'],
            'name': product['name'],
            'description': '',  # TODO: Ürün detay sayfasından açıklama çekilecek
            'price': product['price'][0]['value'],
            'category': product['categoryName'],
            'store': store_id,
            'user': store_data.get('user'),
            'images': [img['linkFormat'].replace('{size}', '1200') for img in product['images']],
            'url': f"https://www.hepsiburada.com{product['productUrl']}",
            'store_type': STORE_TYPE,
            'status': 'published',
            'extra_fields': {
                'brand': product['brandName'],
                'rating': product['rating'],
                'merchant_id': product['merchantId'],
                'merchant_name': product['merchantName'],
                'category_id': product['categoryId']
            }
        }
        
        # Ürünün zaten var olup olmadığını kontrol et
        existing_product = await products_collection.filter(
            (F(sku=product_data['sku']) & F(store=store_id)) | 
            (F(product_id=product_data['product_id']) & F(store=store_id))
        ).read()
        
        if existing_product.items:
            # Ürün varsa güncelle
            updated_product = await products_collection.update(
                existing_product.items[0]['id'], 
                product_data
            )
            print(f"Ürün güncellendi: {product_data['name']}")
        else:
            # Ürün yoksa yeni ekle
            created_product = await products_collection.create(product_data)
            print(f"Yeni ürün eklendi: {product_data['name']}")
        
        # Ürünün yorumlarını çek
        print(f"Yorumlar çekiliyor: {product_data['sku']}")
        await fetch_all_reviews(
            product_data['sku'],
            existing_product.items[0]['id'] if existing_product.items else created_product['id'],
            store_id,
            store_data
        )
            
    except Exception as e:
        print(f"Ürün kaydedilirken hata: {str(e)}")
        print(f"Ürün verisi: {product_data}")

async def fetch_product_reviews(sku: str, from_index: int = 0, size: int = 100) -> Optional[Dict]:
    """Ürün yorumlarını çeken fonksiyon"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0",
        'Accept': 'application/json',
        'Accept-Language': 'tr,en-US;q=0.7,en;q=0.3',
    }
    
    url = f"https://user-content-gw-hermes.hepsiburada.com/queryapi/v2/ApprovedUserContents"
    params = {
        "skuList": sku,
        "from": from_index,
        "size": size
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    print(f"Hata: HTTP {response.status}")
                    return None
                    
                return await response.json()
    except Exception as e:
        print(f"Yorumlar alınırken hata: {str(e)}")
        return None

async def save_reviews(reviews: List[Dict], product_id: str, store_id: str, store_data: Dict):
    try:
        directus_api_url = os.getenv("DIRECTUS_API_URL")
        directus_api_token = os.getenv("DIRECTUS_API_TOKEN")
        directus = await Directus(directus_api_url, token=directus_api_token)

        store_type = STORE_TYPE
        
        for review in reviews:
            # İçerik kontrolü
            if not review.get('review', {}).get('content'):
                print("Boş yorum içeriği, atlaniyor...")
                continue
                
            review_date = datetime.fromisoformat(review['createdAt'].split('+')[0])
            
            # Sentiment hesaplama
            rating = review['star']
            if rating >= 4:
                sentiment = 'positive'
            elif rating == 3:
                sentiment = 'neutral'
            else:
                sentiment = 'negative'
                

            # review_target_id'yi oluştur
            review_target_id = f"{store_type}_{review['id']}"

            merchant_name = 'Bilinmiyor'
            if review.get('order') is not None:
                merchant_name = review['order'].get('merchant', 'Bilinmiyor')

            review_data = {
                'review_target_id': review_target_id,
                'content': review['review']['content'],
                'rating': rating,
                'review_date': review_date.strftime('%Y-%m-%d'),
                'review_created_date': review_date.isoformat(),
                'source': 'hepsiburada',
                'sentiment': sentiment,
                'product': product_id,
                'status': 'published',
                'store': store_id,
                'user': store_data.get('user'),
                'extra_fields': {
                    'customer': review['customer'],
                    'isPurchaseVerified': review['isPurchaseVerified'],
                    'media': review['media'],
                    'merchant': merchant_name,
                }
            }
            
            reviews_collection = directus.collection('reviews')

            # Review'in var olup olmadığını kontrol et
            # print(f"Yorum aranıyor - Review Target ID: {review_target_id}")
            existing_review = await reviews_collection.filter(
                F(review_target_id=review_target_id)
            ).read()
            
            
            if existing_review.items:
                await reviews_collection.update(existing_review.items[0]['id'], review_data)
                print(f"Yorum güncellendi: {review_data['review_target_id']}")
            else:
                await reviews_collection.create(review_data)
                print(f"Yeni yorum eklendi: {review_data['review_target_id']}")

    
    except Exception as e:
        print(f"Yorumlar kaydedilirken hata: {str(e)}")

async def fetch_all_reviews(sku: str, product_id: str, store_id: str, store_data: Dict):
    """Tüm yorumları çeken ve kaydeden fonksiyon"""
    from_index = 0
    size = 100
    
    while True:
        response = await fetch_product_reviews(sku, from_index, size)
        if not response:
            break
            
        reviews = response['data']['approvedUserContent']['approvedUserContentList']
        if not reviews:
            break
            
        await save_reviews(reviews, product_id, store_id, store_data)
        
        # Sonraki sayfa kontrolü
        if not response['links'].get('next'):
            break
            
        from_index += size
        # Rate limiting
        await asyncio.sleep(1)

async def update_import_status(store_id: str, status: str) -> None:
    try:
        directus_api_url = os.getenv("DIRECTUS_API_URL")
        directus_api_token = os.getenv("DIRECTUS_API_TOKEN")
        directus = await Directus(directus_api_url, token=directus_api_token)
        
        stores_collection = directus.collection('stores')
        await stores_collection.update(store_id, {
            'import_status': status
        })
        print(f"Import status güncellendi: {status}")
    except Exception as e:
        print(f"Import status güncellenirken hata: {str(e)}")
