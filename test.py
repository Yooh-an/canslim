import requests

def get_eps_data(cik, tag):
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
    headers = {'User-Agent': 'MyUserAgent/1.0'}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        raise ValueError(f"데이터 조회 실패: CIK {cik}, 태그 {tag}, 상태 코드 {response.status_code}")

# 사용 예시
cik = "0000320193"  # Apple Inc.
tag = "EarningsPerShareDiluted"  # 희석 EPS
data = get_eps_data(cik, tag)
print(data)