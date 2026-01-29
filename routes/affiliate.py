from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from functools import wraps
from models import (
    get_affiliate_by_ref_code, get_affiliate_by_id,
    get_orders_by_affiliate, get_payouts_by_affiliate,
    get_clicks_by_affiliate, get_affiliate_summary
)
from config import Config

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
    """代購業者登入頁面（用 ref_code 登入）"""
    if request.method == 'POST':
        ref_code = request.form.get('ref_code', '').strip().lower()
        
        affiliate = get_affiliate_by_ref_code(ref_code)
        
        if affiliate and affiliate['status'] == 'active':
            session['affiliate_id'] = affiliate['id']
            session['affiliate_name'] = affiliate['name']
            return redirect(url_for('affiliate.dashboard'))
        else:
            return render_template('affiliate/login.html', error='推薦碼無效或已停用')
    
    return render_template('affiliate/login.html')


@affiliate_bp.route('/logout')
def logout():
    """登出"""
    session.pop('affiliate_id', None)
    session.pop('affiliate_name', None)
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
    
    # 最近訂單
    recent_orders = get_orders_by_affiliate(affiliate_id, limit=10)
    
    return render_template('affiliate/dashboard.html', 
                           summary=summary, 
                           recent_orders=recent_orders,
                           config=Config)


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
    
    return render_template('affiliate/orders.html', 
                           orders=orders, 
                           affiliate=affiliate,
                           status_filter=status_filter)


# ============================================
# 佣金記錄
# ============================================

@affiliate_bp.route('/payouts')
@affiliate_required
def payouts():
    """佣金發放記錄"""
    affiliate_id = session.get('affiliate_id')
    
    payouts = get_payouts_by_affiliate(affiliate_id, limit=100)
    affiliate = get_affiliate_by_id(affiliate_id)
    
    return render_template('affiliate/payouts.html', 
                           payouts=payouts, 
                           affiliate=affiliate,
                           config=Config)


# ============================================
# 推廣連結
# ============================================

@affiliate_bp.route('/links')
@affiliate_required
def links():
    """推廣連結頁面"""
    affiliate_id = session.get('affiliate_id')
    affiliate = get_affiliate_by_id(affiliate_id)
    
    if not affiliate:
        return redirect(url_for('affiliate.logout'))
    
    # 產生各種連結
    short_url = f"{Config.SHORT_URL_DOMAIN}/{affiliate['short_code']}"
    direct_url = f"{Config.REDIRECT_TARGET}?ref={affiliate['ref_code']}"
    
    return render_template('affiliate/links.html', 
                           affiliate=affiliate,
                           short_url=short_url,
                           direct_url=direct_url,
                           config=Config)


# ============================================
# API endpoints
# ============================================

@affiliate_bp.route('/api/stats')
@affiliate_required
def api_stats():
    """取得自己的統計數據"""
    affiliate_id = session.get('affiliate_id')
    summary = get_affiliate_summary(affiliate_id)
    return jsonify(summary)


@affiliate_bp.route('/api/orders')
@affiliate_required
def api_orders():
    """取得自己的訂單列表"""
    affiliate_id = session.get('affiliate_id')
    status = request.args.get('status')
    limit = int(request.args.get('limit', 50))
    
    orders = get_orders_by_affiliate(affiliate_id, status=status, limit=limit)
    return jsonify(orders)


@affiliate_bp.route('/api/clicks')
@affiliate_required
def api_clicks():
    """取得自己的點擊記錄"""
    affiliate_id = session.get('affiliate_id')
    limit = int(request.args.get('limit', 100))
    
    clicks = get_clicks_by_affiliate(affiliate_id, limit=limit)
    return jsonify(clicks)
