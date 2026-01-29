from supabase import create_client, Client
from config import Config
import shortuuid
from datetime import datetime, timezone

# 初始化 Supabase client
supabase: Client = None

def init_supabase():
    global supabase
    if Config.SUPABASE_URL and Config.SUPABASE_KEY:
        supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
    return supabase

def get_supabase():
    global supabase
    if supabase is None:
        init_supabase()
    return supabase


# ============================================
# Affiliate（代購業者）操作
# ============================================

def create_affiliate(name: str, email: str = None, domain: str = None, 
                     ref_code: str = None, commission_rate: float = None):
    """建立新的代購業者"""
    db = get_supabase()
    
    # 自動產生 ref_code 如果沒提供
    if not ref_code:
        ref_code = shortuuid.uuid()[:8].lower()
    
    # 產生短網址代碼
    short_code = shortuuid.uuid()[:6].lower()
    
    # 使用預設佣金比例
    if commission_rate is None:
        commission_rate = Config.DEFAULT_COMMISSION_RATE
    
    data = {
        'name': name,
        'email': email,
        'domain': domain,
        'ref_code': ref_code,
        'short_code': short_code,
        'commission_rate': commission_rate,
        'status': 'active'
    }
    
    result = db.table('affiliates').insert(data).execute()
    return result.data[0] if result.data else None


def get_affiliate_by_id(affiliate_id: str):
    """用 ID 取得代購業者"""
    db = get_supabase()
    result = db.table('affiliates').select('*').eq('id', affiliate_id).execute()
    return result.data[0] if result.data else None


def get_affiliate_by_ref_code(ref_code: str):
    """用推薦碼取得代購業者"""
    db = get_supabase()
    result = db.table('affiliates').select('*').eq('ref_code', ref_code).execute()
    return result.data[0] if result.data else None


def get_affiliate_by_short_code(short_code: str):
    """用短網址代碼取得代購業者"""
    db = get_supabase()
    result = db.table('affiliates').select('*').eq('short_code', short_code).execute()
    return result.data[0] if result.data else None


def get_all_affiliates(status: str = None):
    """取得所有代購業者"""
    db = get_supabase()
    query = db.table('affiliates').select('*')
    if status:
        query = query.eq('status', status)
    result = query.order('created_at', desc=True).execute()
    return result.data


def update_affiliate(affiliate_id: str, **kwargs):
    """更新代購業者資料"""
    db = get_supabase()
    result = db.table('affiliates').update(kwargs).eq('id', affiliate_id).execute()
    return result.data[0] if result.data else None


def update_affiliate_stats(affiliate_id: str, clicks: int = 0, orders: int = 0, 
                           sales: float = 0, commission: float = 0):
    """更新代購業者統計數據"""
    db = get_supabase()
    affiliate = get_affiliate_by_id(affiliate_id)
    if not affiliate:
        return None
    
    update_data = {
        'total_clicks': affiliate['total_clicks'] + clicks,
        'total_orders': affiliate['total_orders'] + orders,
        'total_sales': float(affiliate['total_sales']) + sales,
        'total_commission': float(affiliate['total_commission']) + commission,
        'pending_commission': float(affiliate['pending_commission']) + commission
    }
    
    return update_affiliate(affiliate_id, **update_data)


# ============================================
# Click（點擊）操作
# ============================================

def record_click(affiliate_id: str, ip_address: str = None, 
                 user_agent: str = None, referer: str = None, landed_url: str = None):
    """記錄一次點擊"""
    db = get_supabase()
    
    data = {
        'affiliate_id': affiliate_id,
        'ip_address': ip_address,
        'user_agent': user_agent,
        'referer': referer,
        'landed_url': landed_url
    }
    
    result = db.table('clicks').insert(data).execute()
    
    # 更新 affiliate 的點擊數
    if result.data:
        update_affiliate_stats(affiliate_id, clicks=1)
    
    return result.data[0] if result.data else None


def get_clicks_by_affiliate(affiliate_id: str, limit: int = 100):
    """取得代購業者的點擊記錄"""
    db = get_supabase()
    result = db.table('clicks').select('*').eq('affiliate_id', affiliate_id)\
        .order('created_at', desc=True).limit(limit).execute()
    return result.data


# ============================================
# Referral Order（推薦訂單）操作
# ============================================

def create_referral_order(affiliate_id: str, shopify_order_id: str, order_number: str,
                          order_total: float, currency: str = 'JPY', 
                          customer_email: str = None, order_created_at: str = None):
    """建立推薦訂單記錄"""
    db = get_supabase()
    
    # 取得代購業者的佣金比例
    affiliate = get_affiliate_by_id(affiliate_id)
    if not affiliate:
        return None
    
    commission_rate = float(affiliate['commission_rate'])
    commission_amount = round(order_total * commission_rate / 100, 2)
    
    data = {
        'affiliate_id': affiliate_id,
        'shopify_order_id': shopify_order_id,
        'order_number': order_number,
        'order_total': order_total,
        'currency': currency,
        'commission_rate': commission_rate,
        'commission_amount': commission_amount,
        'customer_email': customer_email,
        'order_created_at': order_created_at,
        'status': 'pending'
    }
    
    result = db.table('referral_orders').insert(data).execute()
    
    # 更新 affiliate 統計（但佣金先不算，等出貨確認後再算）
    if result.data:
        update_affiliate_stats(affiliate_id, orders=1, sales=order_total)
    
    return result.data[0] if result.data else None


def get_order_by_shopify_id(shopify_order_id: str):
    """用 Shopify 訂單 ID 取得推薦訂單"""
    db = get_supabase()
    result = db.table('referral_orders').select('*').eq('shopify_order_id', shopify_order_id).execute()
    return result.data[0] if result.data else None


def get_orders_by_affiliate(affiliate_id: str, status: str = None, limit: int = 100):
    """取得代購業者的推薦訂單"""
    db = get_supabase()
    query = db.table('referral_orders').select('*').eq('affiliate_id', affiliate_id)
    if status:
        query = query.eq('status', status)
    result = query.order('created_at', desc=True).limit(limit).execute()
    return result.data


def get_all_orders(status: str = None, limit: int = 100):
    """取得所有推薦訂單"""
    db = get_supabase()
    query = db.table('referral_orders').select('*, affiliates(name, ref_code)')
    if status:
        query = query.eq('status', status)
    result = query.order('created_at', desc=True).limit(limit).execute()
    return result.data


def update_order_status(order_id: str, status: str):
    """更新訂單狀態"""
    db = get_supabase()
    
    update_data = {'status': status}
    
    # 如果是確認（出貨），記錄確認時間並更新佣金
    if status == 'confirmed':
        update_data['confirmed_at'] = datetime.now(timezone.utc).isoformat()
        
        # 取得訂單資訊
        order = db.table('referral_orders').select('*').eq('id', order_id).execute()
        if order.data:
            order = order.data[0]
            # 更新 affiliate 的待發放佣金
            affiliate = get_affiliate_by_id(order['affiliate_id'])
            if affiliate:
                new_pending = float(affiliate['pending_commission']) + float(order['commission_amount'])
                update_affiliate(order['affiliate_id'], pending_commission=new_pending)
    
    # 如果是退款，扣回佣金
    elif status == 'refunded':
        order = db.table('referral_orders').select('*').eq('id', order_id).execute()
        if order.data:
            order = order.data[0]
            if order['status'] == 'confirmed':
                # 已確認的訂單退款，要扣回佣金
                affiliate = get_affiliate_by_id(order['affiliate_id'])
                if affiliate:
                    new_pending = max(0, float(affiliate['pending_commission']) - float(order['commission_amount']))
                    update_affiliate(order['affiliate_id'], pending_commission=new_pending)
    
    result = db.table('referral_orders').update(update_data).eq('id', order_id).execute()
    return result.data[0] if result.data else None


# ============================================
# Payout（佣金發放）操作
# ============================================

def create_payout(affiliate_id: str, amount: float, currency: str = 'JPY',
                  payment_method: str = None, payment_details: str = None, note: str = None):
    """建立佣金發放記錄"""
    db = get_supabase()
    
    data = {
        'affiliate_id': affiliate_id,
        'amount': amount,
        'currency': currency,
        'payment_method': payment_method,
        'payment_details': payment_details,
        'note': note,
        'status': 'completed'
    }
    
    result = db.table('payouts').insert(data).execute()
    
    # 更新 affiliate 的佣金狀態
    if result.data:
        affiliate = get_affiliate_by_id(affiliate_id)
        if affiliate:
            new_pending = max(0, float(affiliate['pending_commission']) - amount)
            new_paid = float(affiliate['paid_commission']) + amount
            update_affiliate(affiliate_id, pending_commission=new_pending, paid_commission=new_paid)
    
    return result.data[0] if result.data else None


def get_payouts_by_affiliate(affiliate_id: str, limit: int = 100):
    """取得代購業者的發放記錄"""
    db = get_supabase()
    result = db.table('payouts').select('*').eq('affiliate_id', affiliate_id)\
        .order('paid_at', desc=True).limit(limit).execute()
    return result.data


def get_all_payouts(limit: int = 100):
    """取得所有發放記錄"""
    db = get_supabase()
    result = db.table('payouts').select('*, affiliates(name, ref_code)')\
        .order('paid_at', desc=True).limit(limit).execute()
    return result.data


# ============================================
# 統計查詢
# ============================================

def get_affiliate_summary(affiliate_id: str):
    """取得代購業者的完整統計摘要"""
    affiliate = get_affiliate_by_id(affiliate_id)
    if not affiliate:
        return None
    
    # 取得各狀態的訂單數
    db = get_supabase()
    
    pending_orders = db.table('referral_orders').select('id', count='exact')\
        .eq('affiliate_id', affiliate_id).eq('status', 'pending').execute()
    
    confirmed_orders = db.table('referral_orders').select('id', count='exact')\
        .eq('affiliate_id', affiliate_id).eq('status', 'confirmed').execute()
    
    return {
        'affiliate': affiliate,
        'pending_orders_count': pending_orders.count if pending_orders else 0,
        'confirmed_orders_count': confirmed_orders.count if confirmed_orders else 0,
        'short_url': f"{Config.SHORT_URL_DOMAIN}/{affiliate['short_code']}"
    }


def get_dashboard_stats():
    """取得管理後台儀表板統計"""
    db = get_supabase()
    
    # 總代購業者數
    affiliates = db.table('affiliates').select('id', count='exact').eq('status', 'active').execute()
    
    # 總訂單數
    orders = db.table('referral_orders').select('id', count='exact').execute()
    
    # 待處理訂單
    pending = db.table('referral_orders').select('id', count='exact').eq('status', 'pending').execute()
    
    # 總銷售額和佣金
    all_affiliates = db.table('affiliates').select('total_sales, total_commission, pending_commission').execute()
    
    total_sales = sum(float(a['total_sales']) for a in all_affiliates.data) if all_affiliates.data else 0
    total_commission = sum(float(a['total_commission']) for a in all_affiliates.data) if all_affiliates.data else 0
    pending_commission = sum(float(a['pending_commission']) for a in all_affiliates.data) if all_affiliates.data else 0
    
    return {
        'total_affiliates': affiliates.count if affiliates else 0,
        'total_orders': orders.count if orders else 0,
        'pending_orders': pending.count if pending else 0,
        'total_sales': total_sales,
        'total_commission': total_commission,
        'pending_commission': pending_commission
    }
