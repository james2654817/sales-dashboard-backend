from flask import Flask, jsonify
from flask_cors import CORS
import requests
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

NOTION_API_KEY = os.environ.get('NOTION_API_KEY')
if not NOTION_API_KEY:
    raise ValueError("NOTION_API_KEY environment variable is required")
NOTION_VERSION = '2022-06-28'

# 資料庫配置
DAILY_REPORT_DB = '279dbea45c5080bfa36ff665c8b26e88'  # 營業日報資料庫（今日數據）
HR_SALES_DB = '1dedbea45c508030bb51fbffeae7e0ae'      # 家根總營業額（大同店 & 安平店本月累計）
MHP_SALES_DB = '1f9dbea45c5081709ea2f400fe43e816'     # 時刻暖鍋營業額（時刻暖鍋本月累計）

def fetch_notion_data(database_id, sorts=None):
    """從 Notion API 獲取指定資料庫的資料"""
    url = f'https://api.notion.com/v1/databases/{database_id}/query'
    headers = {
        'Authorization': f'Bearer {NOTION_API_KEY}',
        'Notion-Version': NOTION_VERSION,
        'Content-Type': 'application/json',
    }
    
    payload = {'page_size': 100}
    if sorts:
        payload['sorts'] = sorts
    
    all_results = []
    has_more = True
    start_cursor = None
    
    # 使用分頁獲取所有數據
    while has_more and len(all_results) < 500:  # 最多獲取500筆
        if start_cursor:
            payload['start_cursor'] = start_cursor
        
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        all_results.extend(data.get('results', []))
        has_more = data.get('has_more', False)
        start_cursor = data.get('next_cursor')
    
    return {'results': all_results}

def get_property_value(properties, property_name, property_type='rich_text'):
    """從 Notion properties 中提取值"""
    prop = properties.get(property_name, {})
    
    if property_type == 'title':
        title_array = prop.get('title', [])
        return title_array[0].get('plain_text', '') if title_array else ''
    elif property_type == 'rich_text':
        text_array = prop.get('rich_text', [])
        return text_array[0].get('plain_text', '') if text_array else ''
    elif property_type == 'number':
        return prop.get('number', 0) or 0
    elif property_type == 'select':
        return prop.get('select', {}).get('name', '')
    elif property_type == 'date':
        date_obj = prop.get('date', {})
        return date_obj.get('start', '') if date_obj else ''
    elif property_type == 'formula':
        formula_obj = prop.get('formula', {})
        return formula_obj.get('number', 0) or 0
    
    return ''

def get_today_data():
    """從營業日報資料庫獲取今日數據"""
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 按日期降序排序，獲取最新數據
    sorts = [{"property": "營業日期", "direction": "descending"}]
    data = fetch_notion_data(DAILY_REPORT_DB, sorts)
    
    stores_today = {}
    
    for page in data.get('results', []):
        props = page.get('properties', {})
        
        store_name = get_property_value(props, '餐廳單位', 'select')
        if not store_name:
            store_name = get_property_value(props, '餐廳單位', 'rich_text')
        
        sales_date = get_property_value(props, '營業日期', 'date')
        sales_amount = get_property_value(props, '營業額', 'number')
        customer_count = get_property_value(props, '來客數', 'number')
        avg_price = get_property_value(props, '客單價', 'number')
        
        # 只處理今日數據
        if sales_date and sales_date.startswith(today):
            # 標準化店名
            if '大同' in store_name:
                display_name = '大同店'
            elif '安平' in store_name:
                display_name = '安平店'
            elif '時刻' in store_name or '暖鍋' in store_name:
                display_name = '時刻暖鍋'
            else:
                display_name = store_name
            
            stores_today[display_name] = {
                'name': display_name,
                'todaySales': sales_amount,
                'todayCustomers': int(customer_count) if customer_count else 0,
                'todayAvgPrice': avg_price,
                'lastUpdate': sales_date
            }
    
    return stores_today

def get_monthly_total_hr():
    """從家根總營業額資料庫獲取大同和安平的本月累計"""
    current_month = datetime.now().strftime('%Y-%m')
    
    # 按日期降序排序
    sorts = [{"property": "營業日期", "direction": "descending"}]
    data = fetch_notion_data(HR_SALES_DB, sorts)
    
    monthly_totals = {
        '大同店': {'total': 0, 'customers': 0},
        '安平店': {'total': 0, 'customers': 0}
    }
    
    for page in data.get('results', []):
        props = page.get('properties', {})
        
        store_name = get_property_value(props, '分店', 'select')
        sales_date = get_property_value(props, '營業日期', 'date')
        total_sales = get_property_value(props, '總營業額', 'formula')
        customer_count = get_property_value(props, '來客數', 'number')
        
        # 確保是本月數據
        if sales_date and sales_date.startswith(current_month):
            if '大同' in store_name:
                monthly_totals['大同店']['total'] += total_sales
                monthly_totals['大同店']['customers'] += customer_count
            elif '安平' in store_name:
                monthly_totals['安平店']['total'] += total_sales
                monthly_totals['安平店']['customers'] += customer_count
    
    return monthly_totals

def get_monthly_total_mhp():
    """從時刻暖鍋營業額資料庫獲取本月累計"""
    current_month = datetime.now().strftime('%Y-%m')
    
    # 按日期降序排序
    sorts = [{"property": "營業日期", "direction": "descending"}]
    data = fetch_notion_data(MHP_SALES_DB, sorts)
    
    monthly_total = {'total': 0, 'customers': 0}
    
    for page in data.get('results', []):
        props = page.get('properties', {})
        
        sales_date = get_property_value(props, '營業日期', 'date')
        total_sales = get_property_value(props, '總營業額', 'formula')
        customer_count = get_property_value(props, '來客數', 'number')
        
        # 確保是本月數據
        if sales_date and sales_date.startswith(current_month):
            monthly_total['total'] += total_sales
            monthly_total['customers'] += customer_count
    
    return monthly_total

@app.route('/api/sales', methods=['GET'])
def get_sales():
    """API 端點：獲取營業額資料"""
    try:
        # 1. 獲取今日數據
        stores_today = get_today_data()
        
        # 2. 獲取本月累計
        hr_monthly = get_monthly_total_hr()
        mhp_monthly = get_monthly_total_mhp()
        
        # 3. 組合數據
        final_data = []
        current_month = datetime.now().strftime('%Y-%m')
        
        # 大同店
        if '大同店' in stores_today:
            store_data = stores_today['大同店']
            store_data['monthlyTotal'] = hr_monthly['大同店']['total']
            store_data['monthlyCustomers'] = hr_monthly['大同店']['customers']
            store_data['dataMonth'] = current_month
            final_data.append(store_data)
        
        # 安平店
        if '安平店' in stores_today:
            store_data = stores_today['安平店']
            store_data['monthlyTotal'] = hr_monthly['安平店']['total']
            store_data['monthlyCustomers'] = hr_monthly['安平店']['customers']
            store_data['dataMonth'] = current_month
            final_data.append(store_data)
        
        # 時刻暖鍋
        if '時刻暖鍋' in stores_today:
            store_data = stores_today['時刻暖鍋']
            store_data['monthlyTotal'] = mhp_monthly['total']
            store_data['monthlyCustomers'] = mhp_monthly['customers']
            store_data['dataMonth'] = current_month
            final_data.append(store_data)
        
        return jsonify({
            'success': True,
            'data': final_data,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康檢查端點"""
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)

