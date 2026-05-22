import os
import json
import logging
import requests
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# 設定日誌記錄
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- 初始化 Firebase ---
def initialize_firebase():
    cred_json_str = os.environ.get("FIREBASE_CRED_JSON")
    if not cred_json_str:
        raise ValueError("⛔ 錯誤：環境變數 FIREBASE_CRED_JSON 未設定")
    cred_dict = json.loads(cred_json_str)
    
    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()

db = initialize_firebase()

# --- 爬蟲核心 (etfinfo.tw) ---
class EtfInfoScraper:
    def __init__(self):
        self.url = "https://etfinfo.tw/active"
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

    def fetch_all_etfs(self):
        logger.info("開始從 etfinfo.tw 抓取資料...")
        try:
            response = requests.get(self.url, headers=self.headers, timeout=15)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 定位表格
            table = soup.find('table', {'class': 'expandable-table'})
            if not table:
                logger.error("無法找到表格結構")
                return []
            
            etf_list = []
            rows = table.find('tbody').find_all('tr', class_='expandable-row')
            
            for row in rows:
                cols = row.find_all('td')
                # 根據 HTML 結構解析內容
                etf_code = cols[1].find('a', class_='code-link').text.strip()
                etf_name = cols[1].find('span', class_='etf-name-sub').text.strip()
                change_str = cols[4].find('strong').text.strip() # 加減碼金額
                
                etf_list.append({
                    "stock_id": etf_code,
                    "stock_name": etf_name,
                    "change": change_str,
                    "timestamp": datetime.now().isoformat()
                })
            return etf_list
        except Exception as e:
            logger.error(f"爬蟲執行錯誤: {e}")
            return []

# --- 量化分析引擎 ---
class QuantEngine:
    def __init__(self, db):
        self.db = db

    def analyze_and_alert(self, etf_data):
        for etf in etf_data:
            # 將資料存入 Firebase，後續可由此處觸發通知或比對邏輯
            self.db.collection('active_etf_daily').document(etf['stock_id']).set(etf)
            logger.info(f"已更新 {etf['stock_id']} {etf['stock_name']} 資料")

# --- 主程式 ---
def main():
    scraper = EtfInfoScraper()
    engine = QuantEngine(db)
    
    etf_data = scraper.fetch_all_etfs()
    if etf_data:
        engine.analyze_and_alert(etf_data)
        logger.info(f"成功處理 {len(etf_data)} 檔 ETF 資料。")
    else:
        logger.warning("未獲取任何 ETF 資料。")

if __name__ == "__main__":
    main()
