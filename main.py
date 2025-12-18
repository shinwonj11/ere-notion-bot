import requests
from bs4 import BeautifulSoup
import time
import re
import os
from datetime import datetime, timedelta

# --- [1. 보안 및 접속 설정] ---
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID")

HEADERS_WEB = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://ere.snu.ac.kr/" # 어디서 왔는지 알려주어 봇 차단을 더 강력히 방지합니다
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

# --- [2. 핵심 함수들] ---

def get_existing_urls():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    try:
        res = requests.post(url, headers=HEADERS_NOTION)
        if res.status_code == 200:
            pages = res.json().get("results", [])
            return [p["properties"]["URL"]["url"] for p in pages if "URL" in p["properties"] and p["properties"]["URL"]["url"]]
    except: pass
    return []

def get_full_date(post_url):
    try:
        res = requests.get(post_url, headers=HEADERS_WEB, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        text = soup.get_text()
        # YY-MM-DD HH:MM 패턴
        match = re.search(r'(\d{2}-\d{2}-\d{2})\s+\d{2}:\d{2}', text)
        if match: return "20" + match.group(1)
        # YYYY-MM-DD 패턴
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
    print("📡 서버 시작... 노션 데이터 조회 중")
    existing_links = get_existing_urls()
    limit_date = datetime.now() - timedelta(days=180) # 6개월 필터
    
    total_added = 0
    for board in ERE_BOARDS:
        print(f"\n🔍 {board['name']} 분석 중...")
        try:
            res = requests.get(board['url'], headers=HEADERS_WEB, timeout=10)
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # [수정] tbody를 제거하고 더 넓은 범위의 tr을 찾습니다. 
            # 그누보드는 보통 .tbl_head01 클래스를 사용합니다.
            rows = soup.select('.tbl_head01 tr') or soup.select('table tr')
            print(f"   📊 검색된 줄 수: {len(rows)}개")
            
            # 만약 여전히 0개라면 서버가 차단한 것이므로 로그를 남깁니다.
            if len(rows) <= 1: # 제목줄만 있거나 아예 없는 경우
                print(f"   ⚠️ 주의: 게시글을 찾지 못했습니다. (응답 코드: {res.status_code})")
                continue

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
                            print(f"   ✅ [전송] {full_date_str} | {title[:15]}...")
                            send_to_notion({"title": title, "link": link, "date": full_date_str, "site": board['name']})
                            total_added += 1
                        else:
                            print(f"   ⏩ [스킵-과거] {full_date_str} | {title[:15]}...")
                    time.sleep(0.3)
        except Exception as e:
            print(f"❌ 에러: {e}")
            
    print(f"\n✨ 작업 완료! 총 {total_added}개의 공지가 추가되었습니다.")

if __name__ == "__main__":
    crawl_and_run()
