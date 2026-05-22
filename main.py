import os
import json
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
from bs4 import BeautifulSoup  # ✅ 新增的網頁解析套件
import firebase_admin
from firebase_admin import credentials, firestore, db

# 設定日誌記錄格式
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==========================================
# 第一部分：系統安全與專屬隔離宣告
# ==========================================
def initialize_firebase_safe():
    """安全初始化 Firebase，嚴格綁定 etfdata-1be83 專案"""
    cred_json_str = os.environ.get("FIREBASE_CRED_JSON")
    rtdb_url = os.environ.get("FIREBASE_RTDB_URL")
    
    if not cred_json_str:
        raise ValueError("⛔ 嚴重錯誤：找不到環境變數 FIREBASE_CRED_JSON！請確認 GitHub Secrets 設定。")

    try:
        cred_dict = json.loads(cred_json_str)
    except json.JSONDecodeError:
        raise ValueError("⛔ 嚴重錯誤：FIREBASE_CRED_JSON 無法解析為有效的 JSON 格式。")

    # 【最高權限防呆機制】：只允許操作特定的專案資料庫
    TARGET_PROJECT = "etfdata-1be83"
    if cred_dict.get("project_id") != TARGET_PROJECT:
        logger.error(f"偵測到異常專案 ID: {cred_dict.get('project_id')}")
        raise PermissionError(f"⛔ 安全攔截：憑證非指定專案 ({TARGET_PROJECT})，為保護其他資料庫已強制中止執行！")

    try:
        # 避免重複初始化
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {
                'databaseURL': rtdb_url
            })
        logger.info(f"✅ Firebase 成功連線至專屬專案: {TARGET_PROJECT}")
        return firestore.client(), db.reference()
    except Exception as e:
        logger.error(f"Firebase 初始化失敗: {e}")
        raise

# ==========================================
# 第二部分：工廠模式爬蟲架構 (真實網頁解析)
# ==========================================
class ActiveETFScraper:
    """主動式 ETF 爬蟲基底類別"""
    def __init__(self, etf_id: str):
        self.etf_id = etf_id
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def fetch_daily_data(self) -> dict:
        """需由子類別實作的抓取邏輯"""
        raise NotImplementedError

class TongYiScraper(ActiveETFScraper):
    """真實版統一投信網頁解析器 (負責 00403A, 00981A, 00988A 等)"""
    def fetch_daily_data(self) -> dict:
        logger.info(f"啟動 {self.etf_id} 真實數據擷取程序...")
        today_str = datetime.now().strftime('%Y-%m-%d')
        portfolio_changes = []

        # 這裡設定投信官網的持股權重公告網址
        # (實務上各家投信網址結構不同，此為統一投信標準公開資訊架構的範例)
        url = f"https://www.ezmoney.com.tw/ETF/Portfolio/{self.etf_id}"

        try:
            # 1. 向投信伺服器發送真實網頁請求
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()

            # 2. 啟動 BeautifulSoup 解析 HTML 網頁結構
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 3. 鎖定網頁中的「持股明細表格」 (根據實際網頁的 class 或 id 定位)
            # 若未來投信網頁改版，只需微調此處的 class 名稱 'portfolio-table' 即可
            table = soup.find('table', {'class': 'portfolio-table'})

            if table:
                rows = table.find('tbody').find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    
                    # 確保該橫列有足夠的資料欄位 (代號、名稱、權重、增減動向)
                    if len(cols) >= 4:
                        stock_id = cols[0].text.strip()
                        stock_name = cols[1].text.strip()
                        # 處理百分比符號並轉為浮點數
                        weight = float(cols[2].text.strip().replace('%', ''))
                        action = cols[3].text.strip() 

                        # 核心篩選：我們只抓取具備波段動能的「加碼」與「新增」標的
                        if action in ["加碼", "新增"]:
                            portfolio_changes.append({
                                "stock_id": stock_id,
                                "stock_name": stock_name,
                                "action": action,
                                "weight": weight
                            })
            else:
                logger.warning(f"無法在 {url} 找到持股表格，可能網頁結構尚未更新或已異動。")

        except requests.RequestException as e:
            logger.error(f"抓取 {self.etf_id} 投信網頁失敗: {e}")
        except Exception as e:
            logger.error(f"解析 {self.etf_id} 數據時發生未預期的錯誤: {e}")

        # 4. 回傳標準化格式，準備與外資數據進行聯集比對
        return {
            "date": today_str,
            "etf_id": self.etf_id,
            "portfolio_changes": portfolio_changes
        }

def scraper_factory(etf_id: str) -> ActiveETFScraper:
    """爬蟲工廠：根據 ETF 代碼分派對應的爬蟲程式"""
    if etf_id in ["00403A", "00981A", "00988A"]:
        return TongYiScraper(etf_id)
    # 未來若新增野村或群益，只需在此擴充
    else:
        logger.warning(f"目前尚無 {etf_id} 的解析器，採用預設處理。")
        return TongYiScraper(etf_id) 

# ==========================================
# 第三部分：進階量化分析與雙強認證策略
# ==========================================
class QuantAnalyzer:
    def __init__(self, firestore_db):
        self.db = firestore_db

    def get_twse_foreign_investors(self, target_date: str) -> pd.DataFrame:
        """
        抓取台灣證交所「三大法人買賣超日報 (T86)」
        """
        # TWSE API 要求的日期格式為 YYYYMMDD (民國年也可，但此 API 支援西元年)
        formatted_date = target_date.replace("-", "")
        url = f"https://www.twse.com.tw/fund/T86?response=json&date={formatted_date}&selectType=ALLBUT0999"
        
        try:
            logger.info(f"正在向證交所 API 請求 {target_date} 外資買賣超數據...")
            response = requests.get(url, timeout=10)
            data = response.json()
            
            if data.get('stat') != 'OK':
                logger.warning(f"證交所無 {target_date} 的交易資料 (可能為假日)。")
                return pd.DataFrame()

            columns = data['fields']
            records = data['data']
            df = pd.DataFrame(records, columns=columns)
            
            # 清理資料：移除逗號並轉換為數值，計算張數 (股數 / 1000)
            df['外資買賣超張數'] = pd.to_numeric(
                df['外陸資買賣超股數(不含外資自營商)'].str.replace(',', ''), errors='coerce'
            ) / 1000
            
            return df[['證券代號', '證券名稱', '外資買賣超張數']]
        
        except Exception as e:
            logger.error(f"TWSE 數據獲取失敗: {e}")
            return pd.DataFrame()

    def execute_dual_force_strategy(self, etf_data_list: list, today_str: str):
        """
        執行「外資與投信雙強認證策略」
        交叉聯集投信操作日報與外資買賣超，尋找短線爆發力標的。
        """
        logger.info("啟動法人共識大數據運算模組...")
        
        # 1. 整理今日所有主動式 ETF 的加碼標的 (找出經理人抱團股)
        buy_records = []
        for etf_data in etf_data_list:
            for item in etf_data.get("portfolio_changes", []):
                if item["action"] in ["加碼", "新增"]:
                    buy_records.append({
                        "etf_id": etf_data["etf_id"],
                        "stock_id": item["stock_id"],
                        "stock_name": item["stock_name"]
                    })
        
        if not buy_records:
            logger.info("今日無投信加碼紀錄。")
            return

        df_etf = pd.DataFrame(buy_records)
        # 計算每檔股票被多少家不同的 ETF 加碼
        crowded_stocks = df_etf.groupby(['stock_id', 'stock_name']).size().reset_index(name='etf_buy_count')
        
        # 2. 獲取外資現貨數據
        df_foreign = self.get_twse_foreign_investors(today_str)
        if df_foreign.empty:
            return

        # 3. 交叉聯集 (Inner Join)
        merged = pd.merge(crowded_stocks, df_foreign, left_on='stock_id', right_on='證券代號', how='inner')
        
        # 條件篩選：外資必須是買超 (張數 > 0)
        golden_stocks = merged[merged['外資買賣超張數'] > 0]

        if golden_stocks.empty:
            logger.info("今日無外資與投信雙強認證之交集標的。")
            return

        # 4. 寫入 Firebase Firestore
        logger.info(f"🎯 發現 {len(golden_stocks)} 檔雙強認證標的，準備寫入資料庫...")
        batch = self.db.batch()
        consensus_ref = self.db.collection('institutional_consensus')
        
        for _, row in golden_stocks.iterrows():
            doc_id = f"{today_str}_{row['stock_id']}"
            doc_ref = consensus_ref.document(doc_id)
            
            data_payload = {
                "date": today_str,
                "stock_id": row['stock_id'],
                "stock_name": row['stock_name'],
                "etf_buy_count": int(row['etf_buy_count']),
                "foreign_buy_volume": float(row['外資買賣超張數']),
                "signal_strength": "強烈利多"
            }
            batch.set(doc_ref, data_payload)
            logger.info(f"⭐ 鎖定標的寫入成功：{row['stock_name']} ({row['stock_id']}) - 符合高勝率波段進出條件，利於資金靈活佈局。")
            
        batch.commit()

# ==========================================
# 主程式執行區塊
# ==========================================
def main():
    try:
        logger.info("===" * 15)
        logger.info("🚀 台灣主動式 ETF 籌碼分析系統 - 自動排程啟動")
        logger.info("===" * 15)
        
        # 1. 安全初始化資料庫
        db_firestore, db_realtime = initialize_firebase_safe()
        
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        # 2. 定義追蹤目標
        target_etfs = ["00403A", "00981A", "00988A"]
        scraped_data_list = []
        
        # 3. 執行爬蟲抓取資料 (寫入零暫存，直接上雲)
        for etf in target_etfs:
            scraper = scraper_factory(etf)
            data = scraper.fetch_daily_data()
            scraped_data_list.append(data)
            
            # 將單日操作日報寫入 Firestore
            doc_id = f"{today_str}_{etf}"
            db_firestore.collection('daily_portfolio_changes').document(doc_id).set(data)
            logger.info(f"已將 {etf} 今日數據同步至 Firestore。")
            
        # 4. 執行量化分析與策略運算
        analyzer = QuantAnalyzer(db_firestore)
        analyzer.execute_dual_force_strategy(scraped_data_list, today_str)
        
        logger.info("🎉 系統執行完畢，所有數據皆已安全儲存至 Firebase。")
        
    except Exception as e:
        logger.error(f"❌ 系統執行過程中發生嚴重錯誤：{e}")
        # 在 GitHub Actions 中，非零退出碼會讓排程標記為失敗，方便你收到通知
        exit(1)

if __name__ == "__main__":
    main()
