from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from models import (
    get_affiliate_by_ref_code, get_affiliate_by_id, update_affiliate,
    get_orders_by_affiliate, get_payouts_by_affiliate, get_clicks_by_affiliate,
    get_affiliate_summary
)
from config import Config
import requests

affiliate_bp = Blueprint('affiliate', __name__, url_prefix='/partner')


def affiliate_required(f):
    """代購業者登入驗證裝飾器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('affiliate_id'):
            return redirect(url_for('affiliate.login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================
# 登入/登出
# ============================================

@affiliate_bp.route('/login', methods=['GET', 'POST'])
def login():
    """代購業者登入頁面"""
    if request.method == 'POST':
        ref_code = request.form.get('ref_code', '').strip()
        
        affiliate = get_affiliate_by_ref_code(ref_code)
        
        if affiliate and affiliate.get('status') == 'active':
            session['affiliate_id'] = affiliate['id']
            session['affiliate_ref_code'] = affiliate['ref_code']
            return redirect(url_for('affiliate.dashboard'))
        else:
            return render_template('affiliate/login.html', error='推薦碼無效或帳戶已停用')
    
    return render_template('affiliate/login.html')


@affiliate_bp.route('/logout')
def logout():
    """登出"""
    session.pop('affiliate_id', None)
    session.pop('affiliate_ref_code', None)
    return redirect(url_for('affiliate.login'))


# ============================================
# 儀表板
# ============================================

@affiliate_bp.route('/')
@affiliate_bp.route('/dashboard')
@affiliate_required
def dashboard():
    """代購業者儀表板"""
    affiliate_id = session.get('affiliate_id')
    summary = get_affiliate_summary(affiliate_id)
    
    if not summary:
        return redirect(url_for('affiliate.logout'))
    
    recent_orders = get_orders_by_affiliate(affiliate_id, limit=5)
    
    return render_template('affiliate/dashboard.html', 
                           summary=summary, recent_orders=recent_orders, config=Config)


# ============================================
# 個人資料
# ============================================

@affiliate_bp.route('/profile', methods=['GET', 'POST'])
@affiliate_required
def profile():
    """個人資料編輯"""
    affiliate_id = session.get('affiliate_id')
    affiliate = get_affiliate_by_id(affiliate_id)
    
    if not affiliate:
        return redirect(url_for('affiliate.logout'))
    
    if request.method == 'POST':
        update_data = {
            'email': request.form.get('email') or None,
            'social_facebook': request.form.get('social_facebook') or None,
            'social_instagram': request.form.get('social_instagram') or None,
            'social_threads': request.form.get('social_threads') or None,
            'social_youtube': request.form.get('social_youtube') or None,
            'social_tiktok': request.form.get('social_tiktok') or None
        }
        
        update_affiliate(affiliate_id, **update_data)
        
        # 重新取得更新後的資料
        affiliate = get_affiliate_by_id(affiliate_id)
        return render_template('affiliate/profile.html', affiliate=affiliate, success=True)
    
    return render_template('affiliate/profile.html', affiliate=affiliate)


# ============================================
# 訂單查詢
# ============================================

@affiliate_bp.route('/orders')
@affiliate_required
def orders():
    """訂單列表"""
    affiliate_id = session.get('affiliate_id')
    status_filter = request.args.get('status')
    
    orders = get_orders_by_affiliate(affiliate_id, status=status_filter, limit=100)
    affiliate = get_affiliate_by_id(affiliate_id)
    
    return render_template('affiliate/orders.html', orders=orders, 
                           affiliate=affiliate, status_filter=status_filter)


# ============================================
# 佣金記錄
# ============================================

@affiliate_bp.route('/payouts')
@affiliate_required
def payouts():
    """發放記錄"""
    affiliate_id = session.get('affiliate_id')
    
    payouts = get_payouts_by_affiliate(affiliate_id, limit=100)
    affiliate = get_affiliate_by_id(affiliate_id)
    
    return render_template('affiliate/payouts.html', payouts=payouts, 
                           affiliate=affiliate, config=Config)


# ============================================
# 推廣連結
# ============================================

@affiliate_bp.route('/links')
@affiliate_required
def links():
    """推廣連結頁面"""
    affiliate_id = session.get('affiliate_id')
    affiliate = get_affiliate_by_id(affiliate_id)
    
    short_url = f"{Config.SHORT_URL_DOMAIN}/{affiliate['short_code']}"
    direct_url = f"{Config.REDIRECT_TARGET}?ref={affiliate['ref_code']}"
    
    return render_template('affiliate/links.html', 
                           affiliate=affiliate, short_url=short_url, 
                           direct_url=direct_url, config=Config)


# ============================================
# 商品搜尋 API
# ============================================

@affiliate_bp.route('/api/products/search')
@affiliate_required
def api_search_products():
    """搜尋 Shopify 商品"""
    query = request.args.get('q', '').strip().lower()
    
    if not query or len(query) < 2:
        return jsonify({'products': [], 'error': '請輸入至少 2 個字'})
    
    try:
        # 呼叫 Shopify Admin API
        shop_domain = Config.SHOPIFY_SHOP_DOMAIN
        access_token = Config.SHOPIFY_ACCESS_TOKEN
        
        if not shop_domain or not access_token:
            return jsonify({'products': [], 'error': 'Shopify API 未設定'})
        
        # 取得所有商品（使用 GraphQL 搜尋會更好，但先用 REST API）
        url = f"https://{shop_domain}/admin/api/2024-01/products.json"
        headers = {
            'X-Shopify-Access-Token': access_token,
            'Content-Type': 'application/json'
        }
        params = {
            'limit': 250,  # 取得更多商品
            'status': 'active'
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code != 200:
            return jsonify({'products': [], 'error': f'API 錯誤: {response.status_code}'})
        
        data = response.json()
        products = []
        
        for product in data.get('products', []):
            # 模糊搜尋：檢查標題是否包含搜尋關鍵字
            title_lower = product.get('title', '').lower()
            
            if query in title_lower:
                # 取得第一個 variant 的價格
                price = '0'
                if product.get('variants'):
                    price = product['variants'][0].get('price', '0')
                
                # 取得第一張圖片
                image_url = ''
                if product.get('images'):
                    image_url = product['images'][0].get('src', '')
                elif product.get('image'):
                    image_url = product['image'].get('src', '')
                
                products.append({
                    'id': product['id'],
                    'title': product['title'],
                    'handle': product['handle'],
                    'price': price,
                    'image': image_url,
                    'url': f"{Config.REDIRECT_TARGET}/products/{product['handle']}"
                })
        
        # 限制回傳數量
        products = products[:20]
        
        return jsonify({'products': products})
        
    except requests.exceptions.Timeout:
        return jsonify({'products': [], 'error': '連線逾時'})
    except Exception as e:
        print(f"Error searching products: {e}")
        return jsonify({'products': [], 'error': '搜尋失敗'})


# ============================================
# API endpoints
# ============================================

@affiliate_bp.route('/api/stats')
@affiliate_required
def api_stats():
    """取得統計數據 API"""
    affiliate_id = session.get('affiliate_id')
    summary = get_affiliate_summary(affiliate_id)
    return jsonify(summary)


@affiliate_bp.route('/api/orders')
@affiliate_required
def api_orders():
    """取得訂單列表 API"""
    affiliate_id = session.get('affiliate_id')
    orders = get_orders_by_affiliate(affiliate_id, limit=50)
    return jsonify(orders)


@affiliate_bp.route('/api/clicks')
@affiliate_required
def api_clicks():
    """取得點擊記錄 API"""
    affiliate_id = session.get('affiliate_id')
    clicks = get_clicks_by_affiliate(affiliate_id, limit=50)
    return jsonify(clicks)
