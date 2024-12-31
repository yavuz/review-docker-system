from typing import Tuple, Dict, Any
from py_directus import Directus, F
from datetime import datetime

class SubscriptionLimits:
    def __init__(self, product_limit: int, review_limit: int, current_products: int, current_reviews: int):
        self.product_limit = product_limit
        self.review_limit = review_limit
        self.current_products = current_products
        self.current_reviews = current_reviews
        self.added_products = 0
        self.added_reviews = 0
    
    def can_add_product(self) -> bool:
        # Ürün limiti 0 ise ürün eklemeye izin verme
        if int(self.product_limit) == 0:
            return False
            
        # Toplam ürün sayısı limitten küçükse True döndür
        return (0 + int(self.added_products)) < int(self.product_limit)
    
    def can_add_review(self) -> bool:
        # Limit 0 ise yorum eklemeye izin verme
        if int(self.review_limit) == 0:
            return False
            
        # Toplam yorum sayısı limitten küçükse True döndür
        return (int(self.current_reviews) + int(self.added_reviews)) < int(self.review_limit)
    
    def add_product(self) -> bool:
        if self.can_add_product():
            self.added_products += 1
            return True
        return False
    
    def add_review(self) -> bool:
        if self.can_add_review():
            self.added_reviews += 1
            return True
        return False
    
    def get_usage_stats(self) -> Tuple[int, int]:
        return self.added_products, self.added_reviews

async def initialize_subscription_limits(directus: Directus, user_id: str) -> Tuple[SubscriptionLimits, Dict]:
    """
    Kullanıcının abonelik limitlerini başlangıçta alır
    """
    try:
        print("User ID: ", user_id)
        # Kullanıcının paket bilgilerini al
        users = directus.collection('directus_users')
        user = await users.filter(F(id=user_id)).read()
        #await directus.collection('directus_users').filter(F(id=user_id)).read()

        print("User: ", user.items)
        
        if not user.items:
            raise Exception(f"Kullanıcı bulunamadı: {user_id}")
            
        package_id = user.items[0].get('package_id')
        print("Package ID: ", package_id)
        if not package_id:
            raise Exception(f"Kullanıcının paketi bulunamadı: {user_id}")
            
        # Paket limitlerini al
        packages = directus.collection('packages')
        package = await packages.filter(id=package_id).read()
        
        if not package.items:
            raise Exception(f"Paket bulunamadı: {package_id}")
            
        package_info = package.items[0]
        product_limit = package_info.get('product_limit', 0)
        review_limit = package_info.get('review_limit', 0)
        
        # Mevcut kullanımı kontrol et
        products = directus.collection('products')
        reviews = directus.collection('reviews')
        
        current_products = await products.filter(user=user_id).aggregate(count="*").read()
        current_reviews = await reviews.filter(user=user_id).aggregate(count="*").read()

        current_products_count = current_products.items[0].get('count') if current_products.items else 0
        current_reviews_count = current_reviews.items[0].get('count') if current_reviews.items else 0
        print("Current products count: ", current_products_count)
        print("Current reviews count: ", current_reviews_count)
        
        limits = SubscriptionLimits(
            product_limit=product_limit,
            review_limit=review_limit,
            current_products=current_products_count,
            current_reviews=current_reviews_count
        )
        
        return limits, package_info
        
    except Exception as e:
        print(f"Limit başlatma sırasında hata: {str(e)}")
        return SubscriptionLimits(0, 0, 0, 0), {}

async def update_subscription_usage(directus: Directus, user_id: str, limits: SubscriptionLimits) -> None:
    """
    Kullanıcının abonelik kullanım istatistiklerini günceller
    """
    try:
        added_products, added_reviews = limits.get_usage_stats()
        if added_products == 0 and added_reviews == 0:
            return
            
        subscription_usage = directus.collection('subscription_usage')
        
        usage = await subscription_usage.filter(
            user_id=user_id
        ).read()
        
        if usage.items:
            current_usage = usage.items[0]
            print("Current product count: ", current_usage.get('product_count', 0))
            print("Current review count: ", current_usage.get('review_count', 0))
            print("Added products: ", added_products)
            print("Added reviews: ", added_reviews)
            await subscription_usage.update(current_usage['id'], {
                'product_count': added_products,
                'review_count': added_reviews
            })
        else:
            await subscription_usage.create({
                'user_id': user_id,
                'product_count': added_products,
                'review_count': added_reviews
            })
            
    except Exception as e:
        print(f"Kullanım istatistikleri güncellenirken hata: {str(e)}")
