import requests
from bs4 import BeautifulSoup
import time
import re
import os
from datetime import datetime, timedelta

# --- [1. 보안 설정] ---
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID")

# ⭐️ 이 부분이 없으면 깃허브 서버에서 빈 페이지를 받게 됩니다
HEADERS_WEB = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}
HEADERS_NOTION = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

ERE_BOARDS = [
    {"name": "ERE-학부공지", "url": "https://ere.snu.ac.kr/bbs/board.php?bo_table=sub5_1"},
    {"name": "ERE-대학원공지", "url": "https://ere.snu.ac.kr/bbs/board.php?bo_table=sub5_2"},
    {"name": "ERE-장학공지", "url": "https://ere.snu.ac.kr/bbs/board.php?bo_table=sub5_3"},
    {"name": "ERE-채용/취업", "url": "https://ere.snu.ac.kr/bbs/board.php?bo_table=sub5_4"},
    {"name": "ERE-행사/세미나", "url": "https://ere.snu.ac.kr/bbs/board.php?bo_table=sub5_5"},
    {"name": "ERE-자유게시판", "url": "https://ere.snu.ac.kr/bbs/board.php?bo_table=sub5_6"},
]

def get_existing_urls():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    try:
        res = requests.post(url, headers=HEADERS_NOTION)
        if res.status_code == 200:
            pages = res.json().get("results", [])
            return [p["properties"]["URL"]["url"] for p in pages if p["properties"]["URL"]["url"]]
    except: pass
    return []

def get_full_date(post_url):
    try:
        res = requests.get(post_url, headers=HEADERS_WEB, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text()
        match = re.search(r'(\d{2}-\d{2}-\d{2})\s+\d{2}:\d{2}', text)
        if match: return "20" + match.group(1)
        match = re.search(r'(\d{4}-\d{2}-\d{2})', text)
        if match: return match.group(1)
    except: pass
    return None

def send_to_notion(item):
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
    print("📡 서버 시작... 노션 중복 데이터 조회 중")
    existing_links = get_existing_urls()
    limit_date = datetime.now() - timedelta(days=180) # 최근 6개월
    
    total_added = 0
    for board in ERE_BOARDS:
        print(f"\n🔍 {board['name']} 분석 중...")
        try:
            # ⭐️ 접속 시 헤더를 반드시 포함합니다
            res = requests.get(board['url'], headers=HEADERS_WEB, timeout=10)
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 실제 게시글이 들어있는 줄(tr)을 찾습니다.
            rows = soup.select('table tbody tr')
            print(f"   📊 검색된 게시글 줄 수: {len(rows)}개") # 이 로그가 0이면 선택자 문제
            
            for row in rows:
                subject_td = row.select_one('.td_subject')
                if not subject_td: continue
                
                target_link = next((a for a in subject_td.select('a') if 'wr_id=' in a.get('href', '')), None)
                if target_link:
                    link = target_link['href']
                    if link in existing_links: continue

                    title = target_link.get_text(strip=True)
                    full_date_str = get_full_date(link)
                    
                    if full_date_str:
                        post_date = datetime.strptime(full_date_str, '%Y-%m-%d')
                        if post_date >= limit_date:
                            print(f"   ✅ [전송] {full_date_str} | {title[:20]}")
                            send_to_notion({"title": title, "link": link, "date": full_date_str, "site": board['name']})
                            total_added += 1
                        else:
                            print(f"   ⏩ [스킵-과거] {full_date_str} | {title[:20]}")
                    time.sleep(0.5)
        except Exception as e:
            print(f"❌ 에러: {e}")
            
    print(f"\n✨ 작업 완료! 총 {total_added}개의 공지가 추가되었습니다.")

if __name__ == "__main__":
    crawl_and_run()
