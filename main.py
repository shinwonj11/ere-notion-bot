import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime, timedelta
import os

# --- [1. 설정 정보] ---
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID")

HEADERS = {
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

# --- [2. 기능 함수들] ---

def get_existing_urls():
    """노션에 이미 저장된 URL 목록을 가져옵니다."""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    res = requests.post(url, headers=HEADERS)
    existing_urls = []
    if res.status_code == 200:
        pages = res.json().get("results", [])
        for page in pages:
            url_val = page["properties"].get("URL", {}).get("url")
            if url_val: existing_urls.append(url_val)
    return existing_urls

def get_full_date(post_url):
    """상세 페이지에서 연도 포함 날짜(YY-MM-DD)를 가져옵니다."""
    try:
        res = requests.get(post_url, timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        date_text = soup.get_text()
        match = re.search(r'(\d{2}-\d{2}-\d{2})', date_text)
        if match:
            return "20" + match.group(1) # '24-12-17' -> '2024-12-17'
    except:
        pass
    return None

def crawl_ere(board, existing_links):
    """6개월 이내의 게시글만 추출합니다."""
    print(f"🔍 {board['name']} 데이터 추출 중...")
    
    # 오늘 기준 6개월 전 날짜 계산 (약 180일)
    six_months_ago = datetime.now() - timedelta(days=180)
    
    try:
        res = requests.get(board['url'], timeout=10)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('table tbody tr')
        data = []
        
        for row in rows:
            subject_td = row.select_one('.td_subject')
            if not subject_td: continue
            
            target_link = None
            for a in subject_td.select('a'):
                href = a.get('href', '')
                if 'wr_id=' in href and 'sca=' not in href:
                    target_link = a
                    break
            
            if target_link:
                link = target_link['href']
                if link in existing_links: continue # 중복 패스

                if target_link.select_one('.bo_cate_link'):
                    target_link.select_one('.bo_cate_link').decompose()
                title = target_link.get_text(strip=True)
                
                # 상세 페이지에서 날짜 확인
                full_date_str = get_full_date(link)
                if full_date_str:
                    # 문자열 날짜를 비교 가능한 날짜 객체로 변환
                    post_date = datetime.strptime(full_date_str, '%Y-%m-%d')
                    
                    # [핵심] 6개월 이내인 경우만 추가
                    if post_date >= six_months_ago:
                        data.append({
                            "title": title, "link": link, 
                            "date": full_date_str, "site": board['name']
                        })
                time.sleep(0.1)
                
        return data
    except Exception as e:
        print(f"❌ 에러: {e}")
        return []

def send_to_notion(item):
    """노션 전송"""
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
    requests.post(url, headers=HEADERS, json=payload)

# --- [3. 메인 실행] ---

if __name__ == "__main__":
    existing_links = get_existing_urls()
    print(f"📊 기존 데이터 확인 완료. {len(existing_links)}개 존재함.")

    new_posts = []
    for board in ERE_BOARDS:
        new_posts.extend(crawl_ere(board, existing_links))
    
    if not new_posts:
        print("✅ 최근 6개월 내의 새로운 공지가 없습니다.")
    else:
        print(f"🚀 {len(new_posts)}개의 새로운 공지를 전송합니다.")
        for post in new_posts:
            send_to_notion(post)
            print(f"✅ 추가됨: {post['title'][:20]}...")

    print("\n✨ 모든 작업이 완료되었습니다!")