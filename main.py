# ==========================================
# 第二部分：工廠模式爬蟲架構 (多投信擴充版)
# ==========================================
class ActiveETFScraper:
    """主動式 ETF 爬蟲基底類別"""
    def __init__(self, etf_id: str):
        self.etf_id = etf_id
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def fetch_daily_data(self) -> dict:
        """預設的回傳格式，避免未實作的解析器導致系統崩潰"""
        return {
            "date": datetime.now().strftime('%Y-%m-%d'),
            "etf_id": self.etf_id,
            "portfolio_changes": []
        }

class TongYiScraper(ActiveETFScraper):
    """真實版統一投信網頁解析器"""
    def fetch_daily_data(self) -> dict:
        # (這裡保留你原本已經寫好的統一投信 BeautifulSoup 爬蟲完整邏輯)
        # ... [程式碼略，請保留原本的邏輯] ...
        pass

class QunYiScraper(ActiveETFScraper):
    """群益投信解析器框架"""
    def fetch_daily_data(self) -> dict:
        logger.info(f"啟動 {self.etf_id} (群益) 數據擷取程序...")
        # TODO: 待補上群益投信專屬的 BeautifulSoup 解析邏輯
        return super().fetch_daily_data()

class FuhwaScraper(ActiveETFScraper):
    """復華投信解析器框架"""
    def fetch_daily_data(self) -> dict:
        logger.info(f"啟動 {self.etf_id} (復華) 數據擷取程序...")
        # TODO: 待補上復華投信專屬的 BeautifulSoup 解析邏輯
        return super().fetch_daily_data()

class YuantaScraper(ActiveETFScraper):
    """元大投信解析器框架"""
    def fetch_daily_data(self) -> dict:
        logger.info(f"啟動 {self.etf_id} (元大) 數據擷取程序...")
        # TODO: 待補上元大投信專屬的 BeautifulSoup 解析邏輯
        return super().fetch_daily_data()

def scraper_factory(etf_id: str) -> ActiveETFScraper:
    """爬蟲工廠：根據 ETF 代碼精準分派對應的投信解析器"""
    
    # 統一投信
    if etf_id in ["00403A", "00981A", "00988A"]:
        return TongYiScraper(etf_id)
        
    # 群益投信 (依據截圖：科技創新、台灣強棒、美國增長)
    elif etf_id in ["00992A", "00982A", "00997A"]:
        return QunYiScraper(etf_id)
        
    # 復華投信 (依據截圖：未來50、金融股息、金融債息)
    elif etf_id in ["00991A", "00998A", "00986D"]:
        return FuhwaScraper(etf_id)
        
    # 元大投信 (依據截圖：AI新經濟)
    elif etf_id in ["00990A"]:
        return YuantaScraper(etf_id)
        
    else:
        logger.warning(f"目前尚無 {etf_id} 的專屬解析器，將跳過該檔數據抓取。")
        return ActiveETFScraper(etf_id) 

# 在主程式的目標清單中，你可以隨時將想追蹤的代碼加入：
# target_etfs = ["00403A", "00981A", "00988A", "00992A", "00991A", "00990A"]
