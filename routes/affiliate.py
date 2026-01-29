from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from models import (
    get_affiliate_by_ref_code, get_affiliate_by_id, update_affiliate,
    get_orders_by_affiliate, get_payouts_by_affiliate, get_clicks_by_affiliate,
    get_affiliate_summary, get_clicks_by_source
)
from config import Config
import requests
import re

affiliate_bp = Blueprint('affiliate', __name__, url_prefix='/partner')


def affiliate_required(f):
    """代購業者登入驗證裝飾器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('affiliate_id'):
            return redirect(url_for('affiliate.login'))
        return f(*args, **kwargs)
    return decorated_function


def normalize_text(text):
    """正規化文字，移除特殊符號方便比對"""
    # 轉小寫
    text = text.lower()
    # 移除常見分隔符號（-、_、空格、.）
    text = re.sub(r'[-_\s\.]', '', text)
    return text


def get_all_shopify_products():
    """取得所有 Shopify 商品（含分頁）"""
    shop_domain = Config.SHOPIFY_SHOP_DOMAIN
    access_token = Config.SHOPIFY_ACCESS_TOKEN
    
    if not shop_domain or not access_token:
        return []
    
    all_products = []
    url = f"https://{shop_domain}/admin/api/2024-01/products.json"
    headers = {
        'X-Shopify-Access-Token': access_token,
        'Content-Type': 'application/json'
    }
    
    params = {
        'limit': 250,
        'status': 'active'
    }
    
    try:
        # 第一頁
        response = requests.get(url, headers=headers, params=params, timeout=15)
        if response.status_code != 200:
            return []
        
        data = response.json()
        all_products.extend(data.get('products', []))
        
        # 檢查是否有下一頁
        while 'Link' in response.headers:
            link_header = response.headers['Link']
            # 解析 Link header 取得下一頁 URL
            if 'rel="next"' not in link_header:
                break
            
            # 取得 next link
            links = link_header.split(',')
            next_url = None
            for link in links:
                if 'rel="next"' in link:
                    next_url = link.split(';')[0].strip().strip('<>')
                    break
            
            if not next_url:
                break
            
            response = requests.get(next_url, headers=headers, timeout=15)
            if response.status_code != 200:
                break
            
            data = response.json()
            products = data.get('products', [])
            if not products:
                break
            
            all_products.extend(products)
            
            # 安全限制，最多取 1000 個商品
            if len(all_products) >= 1000:
                break
        
        return all_products
        
    except Exception as e:
        print(f"Error fetching products: {e}")
        return []


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
    
    # 取得各來源點擊統計
    source_stats = get_clicks_by_source(affiliate_id)
    
    return render_template('affiliate/links.html', 
                           affiliate=affiliate, short_url=short_url, 
                           direct_url=direct_url, config=Config,
                           source_stats=source_stats)


# ============================================
# 商品搜尋 API
# ============================================

@affiliate_bp.route('/api/products/search')
@affiliate_required
def api_search_products():
    """搜尋 Shopify 商品"""
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 2:
        return jsonify({'products': [], 'error': '請輸入至少 2 個字'})
    
    # 正規化搜尋關鍵字
    query_normalized = normalize_text(query)
    
    try:
        # 取得所有商品（含分頁）
        all_products = get_all_shopify_products()
        
        if not all_products:
            return jsonify({'products': [], 'error': '無法取得商品列表'})
        
        # 模糊搜尋：正規化後比對
        matched_products = []
        
        for product in all_products:
            title = product.get('title', '')
            title_normalized = normalize_text(title)
            
            # 檢查正規化後的標題是否包含正規化後的關鍵字
            if query_normalized in title_normalized:
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
                
                matched_products.append({
                    'id': product['id'],
                    'title': title,
                    'handle': product['handle'],
                    'price': price,
                    'image': image_url,
                    'url': f"{Config.REDIRECT_TARGET}/products/{product['handle']}"
                })
        
        # 限制回傳 20 個
        matched_products = matched_products[:20]
        
        return jsonify({
            'products': matched_products,
            'total_found': len(matched_products),
            'shop_url': Config.REDIRECT_TARGET
        })
        
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


@affiliate_bp.route('/api/source-stats')
@affiliate_required
def api_source_stats():
    """取得各來源點擊統計 API"""
    affiliate_id = session.get('affiliate_id')
    stats = get_clicks_by_source(affiliate_id)
    return jsonify(stats)
