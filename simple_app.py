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

# 資料庫 ID（只使用這兩個）
HR_SALES_DB = '1dedbea45c508030bb51fbffeae7e0ae'      # 家根總營業額
MHP_SALES_DB = '1f9dbea45c5081709ea2f400fe43e816'     # 時刻暖鍋營業額

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

def fetch_notion_data(database_id, sorts=None, page_size=100):
    """從 Notion 資料庫獲取數據"""
    url = f'https://api.notion.com/v1/databases/{database_id}/query'
    payload = {'page_size': page_size}
    if sorts:
        payload['sorts'] = sorts
    response = requests.post(url, headers=HEADERS, json=payload, timeout=30)
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

def get_hr_data():
    """從家根總營業額資料庫獲取大同和安平的數據"""
    taiwan_tz = pytz.timezone('Asia/Taipei')
    current_month = datetime.now(taiwan_tz).strftime('%Y-%m')
    
    # 按日期降序排序
    sorts = [{"property": "營業日期", "direction": "descending"}]
    data = fetch_notion_data(HR_SALES_DB, sorts)
    
    # 初始化數據結構
    stores_data = {
        '大同店': {
            'name': '大同店',
            'latestDate': None,
            'todaySales': 0,
            'todayCustomers': 0,
            'todayAvgPrice': 0,
            'monthlyTotal': 0,
            'monthlyCustomers': 0
        },
        '安平店': {
            'name': '安平店',
            'latestDate': None,
            'todaySales': 0,
            'todayCustomers': 0,
            'todayAvgPrice': 0,
            'monthlyTotal': 0,
            'monthlyCustomers': 0
        }
    }
    
    for page in data.get('results', []):
        props = page.get('properties', {})
        
        sales_date = get_property_value(props, '營業日期', 'date')
        branch = get_property_value(props, '分店', 'select')
        total_sales = get_property_value(props, '總營業額', 'formula')
        customer_count = get_property_value(props, '來客數', 'number')
        avg_price = get_property_value(props, '客單價', 'formula')
        
        # 判斷是哪家店
        if '大同' in branch:
            store_key = '大同店'
        elif '安平' in branch:
            store_key = '安平店'
        else:
            continue
        
        # 記錄最新一筆數據（用於顯示今日營業額）
        if stores_data[store_key]['latestDate'] is None:
            stores_data[store_key]['latestDate'] = sales_date
            stores_data[store_key]['todaySales'] = total_sales
            stores_data[store_key]['todayCustomers'] = int(customer_count) if customer_count else 0
            stores_data[store_key]['todayAvgPrice'] = avg_price
        
        # 累計本月數據
        if sales_date and sales_date.startswith(current_month):
            stores_data[store_key]['monthlyTotal'] += total_sales
            stores_data[store_key]['monthlyCustomers'] += int(customer_count) if customer_count else 0
    
    return stores_data

def get_mhp_data():
    """從時刻暖鍋營業額資料庫獲取數據"""
    taiwan_tz = pytz.timezone('Asia/Taipei')
    current_month = datetime.now(taiwan_tz).strftime('%Y-%m')
    
    # 按日期降序排序
    sorts = [{"property": "營業日期", "direction": "descending"}]
    data = fetch_notion_data(MHP_SALES_DB, sorts)
    
    # 初始化數據結構
    store_data = {
        'name': '時刻暖鍋',
        'latestDate': None,
        'todaySales': 0,
        'todayCustomers': 0,
        'todayAvgPrice': 0,
        'monthlyTotal': 0,
        'monthlyCustomers': 0
    }
    
    for page in data.get('results', []):
        props = page.get('properties', {})
        
        sales_date = get_property_value(props, '營業日期', 'date')
        total_sales = get_property_value(props, '實收現金', 'formula')
        customer_count = get_property_value(props, '來客數', 'number')
        avg_price = get_property_value(props, '客單價', 'formula')
        
        # 記錄最新一筆數據
        if store_data['latestDate'] is None:
            store_data['latestDate'] = sales_date
            store_data['todaySales'] = total_sales
            store_data['todayCustomers'] = int(customer_count) if customer_count else 0
            store_data['todayAvgPrice'] = avg_price
        
        # 累計本月數據
        if sales_date and sales_date.startswith(current_month):
            store_data['monthlyTotal'] += total_sales
            store_data['monthlyCustomers'] += int(customer_count) if customer_count else 0
    
    return store_data

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
        taiwan_tz = pytz.timezone('Asia/Taipei')
        current_month = datetime.now(taiwan_tz).strftime('%Y-%m')
        today = datetime.now(taiwan_tz).strftime('%Y-%m-%d')
        
        # 獲取所有店面數據
        hr_data = get_hr_data()
        mhp_data = get_mhp_data()
        
        # 根據權限決定要顯示哪些店面
        final_data = []
        
        if permission == 'hr':
            # 家根儀表板：只顯示大同和安平
            for store_name in ['大同店', '安平店']:
                store = hr_data[store_name]
                store['dataMonth'] = current_month
                store['lastUpdate'] = store['latestDate']
                store['isToday'] = (store['latestDate'] == today)
                final_data.append(store)
                
        elif permission == 'mhp':
            # 時刻儀表板：只顯示時刻暖鍋
            mhp_data['dataMonth'] = current_month
            mhp_data['lastUpdate'] = mhp_data['latestDate']
            mhp_data['isToday'] = (mhp_data['latestDate'] == today)
            final_data.append(mhp_data)
            
        else:
            # 全店儀表板：顯示所有店面
            for store_name in ['大同店', '安平店']:
                store = hr_data[store_name]
                store['dataMonth'] = current_month
                store['lastUpdate'] = store['latestDate']
                store['isToday'] = (store['latestDate'] == today)
                final_data.append(store)
            
            mhp_data['dataMonth'] = current_month
            mhp_data['lastUpdate'] = mhp_data['latestDate']
            mhp_data['isToday'] = (mhp_data['latestDate'] == today)
            final_data.append(mhp_data)
        
        # 計算今日總營業額（只計算今天的數據）
        today_total = sum(store['todaySales'] for store in final_data if store.get('isToday', False))
        
        return jsonify({
            'success': True,
            'data': final_data,
            'todayTotal': today_total,
            'todayDate': today,
            'timestamp': datetime.now(taiwan_tz).isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
