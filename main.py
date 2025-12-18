import requests
from bs4 import BeautifulSoup
import time
import re
import os
from datetime import datetime, timedelta

# --- [1. 보안 설정: GitHub Secrets에서 가져오기] ---
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID")

# 서버 차단을 피하기 위한 브라우저 정보
HEADERS_WEB = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

HEADERS_NOTION = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# --- [2. 게시판 목록] ---
ERE_BOARDS = [
    {"name": "ERE-학부공지", "url": "https://ere.snu.ac.kr/bbs/board.php?bo_table=sub5_1"},
    {"name": "ERE-대학원공지", "url": "https://ere.snu.ac.kr/bbs/board.php?bo_table=sub5_2"},
    {"name": "ERE-장학공지", "url": "https://ere.snu.ac.kr/bbs/board.php?bo_table=sub5_3"},
    {"name": "ERE-채용/취업", "url": "https://ere.snu.ac.kr/bbs/board.php?bo_table=sub5_4"},
    {"name": "ERE-행사/세미나", "url": "https://ere.snu.ac.kr/bbs/board.php?bo_table=sub5_5"},
    {"name": "ERE-자유게시판", "url": "https://ere.snu.ac.kr/bbs/board.php?bo_table=sub5_6"},
]

# --- [3. 핵심 기능 함수들] ---

def get_existing_urls():
    """노션 중복 체크용 URL 가져오기"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    try:
        res = requests.post(url, headers=HEADERS_NOTION)
        if res.status_code == 200:
            pages = res.json().get("results", [])
            return [p["properties"]["URL"]["url"] for p in pages if p["properties"]["URL"]["url"]]
    except: pass
    return []

def get_full_date(post_url):
    """상세 페이지에서 연도 포함 날짜 추출"""
    try:
        res = requests.get(post_url, headers=HEADERS_WEB, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        date_text = soup.get_text()
        # YY-MM-DD HH:MM 패턴 매칭
        match = re.search(r'(\d{2}-\d{2}-\d{2})\s+\d{2}:\d{2}', date_text)
        if match: return "20" + match.group(1)
    except: pass
    return None

def send_to_notion(item):
    """노션에 페이지 생성"""
    url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": { "database_id": DATABASE_ID },
        "properties": {
            "제목": { "title": [{ "text": { "content": item['title'] } }] },
            "웹사이트": { "select": { "name": item['site'] } },
            "URL": { "url": item['link'] },
            "게시일": { "rich_text": [{ "text": { "content": item['date'] } }] },
            "확인 여부": { "checkbox": False }
        }
    }
    requests.post(url, headers=HEADERS_NOTION, json=payload)

def crawl_and_run():
    print("📡 데이터 확인 및 크롤링 시작...")
    existing_links = get_existing_urls()
    six_months_ago = datetime.now() - timedelta(days=180)
    
    for board in ERE_BOARDS:
        print(f"🔍 {board['name']} 분석 중...")
        try:
            res = requests.get(board['url'], headers=HEADERS_WEB, timeout=10)
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('table tbody tr')
            
            for row in rows:
                subject_td = row.select_one('.td_subject')
                if not subject_td: continue
                
                # wr_id가 포함된 진짜 링크 찾기
                target_link = next((a for a in subject_td.select('a') if 'wr_id=' in a.get('href', '')), None)
                if target_link:
                    link = target_link['href']
                    if link in existing_links: continue # 중복 패스

                    if target_link.select_one('.bo_cate_link'):
                        target_link.select_one('.bo_cate_link').decompose()
                    
                    title = target_link.get_text(strip=True)
                    full_date_str = get_full_date(link)
                    
                    if full_date_str:
                        post_date = datetime.strptime(full_date_str, '%Y-%m-%d')
                        if post_date >= six_months_ago:
                            print(f"   ✅ [추가] {full_date_str} | {title[:15]}...")
                            send_to_notion({"title": title, "link": link, "date": full_date_str, "site": board['name']})
                    time.sleep(0.5)
        except Exception as e:
            print(f"❌ {board['name']} 에러: {e}")

if __name__ == "__main__":
    crawl_and_run()
    print("\n✨ 모든 작업 완료!")
