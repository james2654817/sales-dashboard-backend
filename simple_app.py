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


# 定義所有資料庫的 ID 和其對應的店名欄位
DATABASE_CONFIGS = [
    {
        'id': '1dedbea45c508030bb51fbffeae7e0ae', # HR營業額資料
        'store_name_property': '分店',
        'sales_date_property': '營業日期',
        'total_sales_property': '總營業額',
        'customer_count_property': '來客數',
        'avg_price_property': '客單價',
        'cash_property': '現金',
        'transfer_property': '匯款',
    },
    {
        'id': '1f9dbea45c5081709ea2f400fe43e816', # 時刻暖鍋營業額
        'store_name_property': '店名', # 假設時刻暖鍋資料庫有明確的店名欄位，若無則需調整
        'sales_date_property': '營業日期',
        'total_sales_property': '總營業額',
        'customer_count_property': '來客數',
        'avg_price_property': '客單價',
        'cash_property': '實收現金', # 時刻暖鍋的現金欄位名稱
        'transfer_property': '轉帳',
    }
]

def fetch_notion_data(database_id):
    """從 Notion API 獲取指定資料庫的資料"""
    url = f'https://api.notion.com/v1/databases/{database_id}/query'
    headers = {
        'Authorization': f'Bearer {NOTION_API_KEY}',
        'Notion-Version': NOTION_VERSION,
        'Content-Type': 'application/json',
    }
    
    response = requests.post(url, headers=headers, json={'page_size': 100})
    response.raise_for_status()
    return response.json()

def process_sales_data(results, config):
    """處理單一資料庫的營業額資料"""
    stores = {}
    current_month = datetime.now().strftime('%Y-%m')
    
    for page in results:
        properties = page.get('properties', {})
        
        store_name = properties.get(config['store_name_property'], {}).get('select', {}).get('name', '未知店面')
        sales_date = properties.get(config['sales_date_property'], {}).get('date', {}).get('start')
        total_sales = properties.get(config['total_sales_property'], {}).get('formula', {}).get('number', 0)
        customer_count = properties.get(config['customer_count_property'], {}).get('number', 0)
        avg_price = properties.get(config['avg_price_property'], {}).get('formula', {}).get('number', 0)
        cash = properties.get(config['cash_property'], {}).get('number', 0)
        transfer = properties.get(config['transfer_property'], {}).get('number', 0)

        # 如果時刻暖鍋沒有分店欄位，則直接使用固定店名
        if config['id'] == '1f9dbea45c5081709ea2f400fe43e816' and store_name == '未知店面':
            store_name = '時刻暖鍋'

        if store_name not in stores:
            stores[store_name] = {
                'name': store_name,
                'todaySales': 0,
                'todayCustomers': 0,
                'todayAvgPrice': 0,
                'monthlyTotal': 0,
                'lastUpdate': None,
                'dataMonth': None,
            }
        
        if sales_date:
            stores[store_name]['monthlyTotal'] += total_sales or 0
            if not stores[store_name]['dataMonth']:
                stores[store_name]['dataMonth'] = sales_date[:7]
            
            if not stores[store_name]['lastUpdate'] or (sales_date and sales_date > stores[store_name]['lastUpdate']):
                stores[store_name]['lastUpdate'] = sales_date
                stores[store_name]['todaySales'] = total_sales or 0
                stores[store_name]['todayCustomers'] = customer_count or 0
                stores[store_name]['todayAvgPrice'] = avg_price or 0
    
    return stores

@app.route('/api/sales', methods=['GET'])
def get_sales():
    """API 端點：獲取營業額資料"""
    try:
        all_stores_data = {}
        for config in DATABASE_CONFIGS:
            notion_data = fetch_notion_data(config['id'])
            processed_data = process_sales_data(notion_data.get('results', []), config)
            all_stores_data.update(processed_data)

        # 排序記錄 (此處已在 process_sales_data 中處理，但如果需要對所有店面進行排序，可以在此處添加)
        # for store in all_stores_data.values():
        #     store['records'].sort(key=lambda x: x['date'] or '', reverse=True)

        return jsonify({
            'success': True,
            'data': list(all_stores_data.values()),
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

