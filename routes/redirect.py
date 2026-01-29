from flask import Blueprint, redirect, request
from models import get_affiliate_by_short_code, record_click
from config import Config

redirect_bp = Blueprint('redirect', __name__)


@redirect_bp.route('/<short_code>')
def redirect_short_url(short_code):
    """
    短網址重新導向
    例如：https://go.goyoulink.com/abc123
    會重新導向到：https://goyoutati.com?ref=代購業者的ref_code
    """
    
    # 查詢短網址對應的代購業者
    affiliate = get_affiliate_by_short_code(short_code)
    
    if not affiliate:
        # 找不到，導向主站首頁
        return redirect(Config.REDIRECT_TARGET)
    
    if affiliate['status'] != 'active':
        # 已停用，導向主站首頁
        return redirect(Config.REDIRECT_TARGET)
    
    # 記錄點擊
    record_click(
        affiliate_id=affiliate['id'],
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        referer=request.headers.get('Referer'),
        landed_url=request.url
    )
    
    # 組合目標網址，帶上推薦碼
    target_url = f"{Config.REDIRECT_TARGET}?ref={affiliate['ref_code']}"
    
    return redirect(target_url)


@redirect_bp.route('/<short_code>/<path:product_path>')
def redirect_short_url_with_path(short_code, product_path):
    """
    短網址重新導向（帶商品路徑）
    例如：https://go.goyoulink.com/abc123/products/yokumoku-cigare
    會重新導向到：https://goyoutati.com/products/yokumoku-cigare?ref=xxx
    """
    
    affiliate = get_affiliate_by_short_code(short_code)
    
    if not affiliate:
        return redirect(f"{Config.REDIRECT_TARGET}/{product_path}")
    
    if affiliate['status'] != 'active':
        return redirect(f"{Config.REDIRECT_TARGET}/{product_path}")
    
    # 記錄點擊
    record_click(
        affiliate_id=affiliate['id'],
        ip_address=request.remote_addr,
        user_agent=request.headers.get('User-Agent'),
        referer=request.headers.get('Referer'),
        landed_url=request.url
    )
    
    # 組合目標網址
    target_url = f"{Config.REDIRECT_TARGET}/{product_path}?ref={affiliate['ref_code']}"
    
    return redirect(target_url)
