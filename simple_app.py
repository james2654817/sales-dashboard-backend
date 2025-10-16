from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from datetime import datetime, timedelta
import pytz
import os
import jwt

app = Flask(__name__)
CORS(app)

# JWT 密鑰
JWT_SECRET = os.environ.get('JWT_SECRET', 'your-secret-key-change-this-in-production')
JWT_ALGORITHM = 'HS256'
JWT_EXP_DELTA_HOURS = 24

# Notion API 設定
NOTION_API_KEY = os.environ.get('NOTION_API_KEY')
NOTION_VERSION = '2022-06-28'
HEADERS = {
    'Authorization': f'Bearer {NOTION_API_KEY}',
    'Notion-Version': NOTION_VERSION,
    'Content-Type': 'application/json'
}

# 資料庫 ID
DAILY_REPORT_DB = '279dbea45c5080bfa36ff665c8b26e88'
HR_SALES_DB = '1dedbea45c508030bb51fbffeae7e0ae'
MHP_SALES_DB = '1f9dbea45c5081709ea2f400fe43e816'

def get_users():
    """從環境變數讀取使用者資料"""
    users_str = os.environ.get('USERS', 'james:0204:all,hr:257257:hr,mhp:262626:mhp')
    users = {}
    for user_data in users_str.split(','):
        parts = user_data.strip().split(':')
        if len(parts) == 3:
            username, password, permission = parts
            users[username] = {
                'password': password,
                'permission': permission
            }
    return users

def verify_token(token):
    """驗證 JWT Token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except:
        return None

def fetch_notion_data(database_id, sorts=None):
    """從 Notion 資料庫獲取數據"""
    url = f'https://api.notion.com/v1/databases/{database_id}/query'
    payload = {}
    if sorts:
        payload['sorts'] = sorts
    response = requests.post(url, headers=HEADERS, json=payload)
    return response.json()

def get_property_value(properties, prop_name, prop_type):
    """從 Notion 屬性中提取值"""
    if prop_name not in properties:
        return None
    prop = properties[prop_name]
    if prop_type == 'select':
        select_obj = prop.get('select')
        return select_obj.get('name', '') if select_obj else ''
    elif prop_type == 'number':
        return prop.get('number', 0) or 0
    elif prop_type == 'date':
        date_obj = prop.get('date')
        return date_obj.get('start', '') if date_obj else ''
    elif prop_type == 'formula':
        formula_obj = prop.get('formula')
        return formula_obj.get('number', 0) or 0 if formula_obj else 0
    return ''

def get_latest_data():
    """獲取最近一筆營業數據"""
    sorts = [{"property": "營業日期", "direction": "descending"}]
    data = fetch_notion_data(DAILY_REPORT_DB, sorts)
    stores_latest = {}
    for page in data.get('results', []):
        props = page.get('properties', {})
        store_name = get_property_value(props, '餐廳單位', 'select')
        if '大同' in store_name:
            display_name = '大同店'
        elif '安平' in store_name:
            display_name = '安平店'
        elif '時刻' in store_name or '暖鍋' in store_name:
            display_name = '時刻暖鍋'
        else:
            continue
        if display_name not in stores_latest:
            stores_latest[display_name] = {
                'name': display_name,
                'todaySales': get_property_value(props, '營業額', 'number'),
                'todayCustomers': int(get_property_value(props, '來客數', 'number') or 0),
                'todayAvgPrice': get_property_value(props, '客單價', 'number'),
                'lastUpdate': get_property_value(props, '營業日期', 'date')
            }
    return stores_latest

def get_monthly_total_hr():
    """獲取家根本月累計"""
    taiwan_tz = pytz.timezone('Asia/Taipei')
    current_month = datetime.now(taiwan_tz).strftime('%Y-%m')
    sorts = [{"property": "營業日期", "direction": "descending"}]
    data = fetch_notion_data(HR_SALES_DB, sorts)
    monthly_totals = {'大同店': {'total': 0, 'customers': 0}, '安平店': {'total': 0, 'customers': 0}}
    for page in data.get('results', []):
        props = page.get('properties', {})
        sales_date = get_property_value(props, '營業日期', 'date')
        if sales_date and sales_date.startswith(current_month):
            branch = get_property_value(props, '分店', 'select')
            total_sales = get_property_value(props, '總營業額', 'formula')
            customer_count = get_property_value(props, '來客數', 'number')
            if '大同' in branch:
                monthly_totals['大同店']['total'] += total_sales
                monthly_totals['大同店']['customers'] += customer_count
            elif '安平' in branch:
                monthly_totals['安平店']['total'] += total_sales
                monthly_totals['安平店']['customers'] += customer_count
    return monthly_totals

def get_monthly_total_mhp():
    """獲取時刻暖鍋本月累計"""
    taiwan_tz = pytz.timezone('Asia/Taipei')
    current_month = datetime.now(taiwan_tz).strftime('%Y-%m')
    sorts = [{"property": "營業日期", "direction": "descending"}]
    data = fetch_notion_data(MHP_SALES_DB, sorts)
    monthly_total = {'total': 0, 'customers': 0}
    for page in data.get('results', []):
        props = page.get('properties', {})
        sales_date = get_property_value(props, '營業日期', 'date')
        if sales_date and sales_date.startswith(current_month):
            monthly_total['total'] += get_property_value(props, '實收現金', 'formula')
            monthly_total['customers'] += get_property_value(props, '來客數', 'number')
    return monthly_total

@app.route('/api/login', methods=['POST'])
def login():
    """登入 API"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        if not username or not password:
            return jsonify({'success': False, 'error': '請提供帳號和密碼'}), 400
        users = get_users()
        if username not in users or users[username]['password'] != password:
            return jsonify({'success': False, 'error': '帳號或密碼錯誤'}), 401
        taiwan_tz = pytz.timezone('Asia/Taipei')
        payload = {
            'username': username,
            'permission': users[username]['permission'],
            'exp': datetime.now(taiwan_tz) + timedelta(hours=JWT_EXP_DELTA_HOURS)
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return jsonify({'success': True, 'token': token, 'username': username, 'permission': users[username]['permission']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sales', methods=['GET'])
def get_sales():
    """獲取營業額資料（需要登入）"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': '未提供驗證 Token'}), 401
        token = auth_header.split(' ')[1]
        payload = verify_token(token)
        if not payload:
            return jsonify({'success': False, 'error': 'Token 無效或已過期'}), 401
        permission = payload.get('permission', 'all')
        stores_latest = get_latest_data()
        hr_monthly = get_monthly_total_hr()
        mhp_monthly = get_monthly_total_mhp()
        taiwan_tz = pytz.timezone('Asia/Taipei')
        current_month = datetime.now(taiwan_tz).strftime('%Y-%m')
        today = datetime.now(taiwan_tz).strftime('%Y-%m-%d')
        if permission == 'hr':
            store_names = ['大同店', '安平店']
        elif permission == 'mhp':
            store_names = ['時刻暖鍋']
        else:
            store_names = ['大同店', '安平店', '時刻暖鍋']
        final_data = []
        for store_name in store_names:
            if store_name in ['大同店', '安平店']:
                store_data = stores_latest.get(store_name, {'name': store_name, 'todaySales': 0, 'todayCustomers': 0, 'todayAvgPrice': 0, 'lastUpdate': ''})
                store_data['monthlyTotal'] = hr_monthly[store_name]['total']
                store_data['monthlyCustomers'] = hr_monthly[store_name]['customers']
                store_data['dataMonth'] = current_month
                store_data['isToday'] = (store_data['lastUpdate'] == today)
                final_data.append(store_data)
            elif store_name == '時刻暖鍋':
                store_data = stores_latest.get(store_name, {'name': store_name, 'todaySales': 0, 'todayCustomers': 0, 'todayAvgPrice': 0, 'lastUpdate': ''})
                store_data['monthlyTotal'] = mhp_monthly['total']
                store_data['monthlyCustomers'] = mhp_monthly['customers']
                store_data['dataMonth'] = current_month
                store_data['isToday'] = (store_data['lastUpdate'] == today)
                final_data.append(store_data)
        today_total = sum(store['todaySales'] for store in final_data if store.get('isToday', False))
        return jsonify({'success': True, 'data': final_data, 'todayTotal': today_total, 'todayDate': today, 'timestamp': datetime.now(taiwan_tz).isoformat()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
