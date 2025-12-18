import requests
from bs4 import BeautifulSoup
import time
import re
import os
from datetime import datetime, timedelta

# --- [1. 설정 정보] ---
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
DATABASE_ID = os.environ.get("DATABASE_ID")

# 서버 차단을 피하기 위한 브라우저 정보 설정
HEADERS_WEB = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

HEADERS_NOTION = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# --- [2. 기능 함수들] ---

def get_full_date(post_url):
    """상세 페이지 접속 시 헤더 추가"""
    try:
        # 브라우저인 것처럼 헤더를 넣어서 접속합니다
        res = requests.get(post_url, headers=HEADERS_WEB, timeout=10)
        res.encoding = 'utf-8'
        
        # 만약 차단당했다면 응답 코드가 200이 아닐 것입니다
        if res.status_code != 200:
            print(f"      ⚠️ 접속 실패 (코드 {res.status_code}): {post_url}")
            return None

        soup = BeautifulSoup(res.text, 'html.parser')
        date_text = soup.get_text()
        # YY-MM-DD HH:MM 패턴 매칭
        match = re.search(r'(\d{2}-\d{2}-\d{2})\s+\d{2}:\d{2}', date_text)
        
        if match:
            return "20" + match.group(1)
    except Exception as e:
        print(f"      ⚠️ 날짜 파싱 에러: {e}")
    return None

def crawl_ere(board, existing_links):
    """서버 로그 기능을 강화한 크롤링"""
    print(f"🔍 {board['name']} 분석 시작...")
    six_months_ago = datetime.now() - timedelta(days=180)
    data = []
    
    try:
        res = requests.get(board['url'], headers=HEADERS_WEB, timeout=10)
        res.encoding = 'utf-8'
        
        if res.status_code != 200:
            print(f"   ❌ 게시판 접속 차단됨 (코드 {res.status_code})")
            return []

        soup = BeautifulSoup(res.text, 'html.parser')
        rows = soup.select('table tbody tr')
        
        # 긁어온 행이 몇 개인지 확인
        print(f"   📊 발견된 게시글 행: {len(rows)}개")
        
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
                    if post_date >= six_months_ago:
                        print(f"   ✅ [추가] {full_date_str} | {title[:15]}")
                        data.append({"title": title, "link": link, "date": full_date_str, "site": board['name']})
                    else:
                        print(f"   ⏩ [과거] {full_date_str} | {title[:15]}")
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
