# Growth Stock Screener PRD

## 소개
Growth Stock Screener는 투자자들이 SEC EDGAR 데이터베이스에서 제공하는 재무 데이터를 활용하여 성장 가능성이 높은 미국 상장 주식을 식별할 수 있도록 설계된 Python 애플리케이션입니다. 이 도구는 윌리엄 오닐의 CAN SLIM 전략과 마크 미너비니의 성장 주식 접근법을 기반으로 하여, 최근 몇 분기 동안 강한 재무 성과와 주가 성과를 보이는 주식을 자동으로 검색합니다.

## 목표
- 투자자들이 무료로 접근 가능한 SEC 데이터를 활용하여 성장 주식을 분석할 수 있는 도구 제공
- 데이터 수집 및 분석 프로세스 자동화
- 사용자가 스크리닝 기준을 자유롭게 커스터마이징할 수 있도록 지원
- 분석 결과를 CSV 형식의 보고서로 제공하여 쉽게 활용 가능하도록 함

## 주요 기능
- **SEC EDGAR 대량 데이터 다운로드**: 제출 내역 및 XBRL 회사 사실 데이터를 가져옴
- **재무 데이터 파싱**: SEC 데이터에서 주요 재무 메트릭 계산
- **사용자 정의 필터 적용**: 재무 및 성과 기준에 따라 주식 선별
- **주가 데이터 통합**: yfinance를 통해 주가 성과 분석 (SEC API 외부 소스)
- **선택적 기관 소유 데이터**: 사용자가 API 키를 제공할 경우 추가 필터 적용
- **CSV 보고서 생성**: 스크리닝 결과를 정리하여 출력

## 기능 요구 사항

### 4.1 데이터 다운로드
**설명**: 애플리케이션은 SEC EDGAR에서 제공하는 대량 데이터(제출 내역 및 XBRL 회사 사실)를 다운로드합니다.

**세부 사항**:
- SEC API의 대량 데이터 엔드포인트(예: submissions bulk file, XBRL company facts)를 사용
- 다운로드된 파일은 로컬 디렉토리에 저장됨
- 대용량 파일 처리를 위해 다운로드 중단 시 재개 기능 지원

**명령**: `python growth_stock_screener.py --mode download`

### 4.2 데이터 파싱
**설명**: 다운로드된 데이터를 파싱하여 각 회사의 재무 메트릭을 계산하고 저장합니다.

**세부 사항**:
- **회사 목록 추출**: submissions 파일에서 CIK(회사 식별 번호)와 회사명 추출
- **XBRL 데이터 처리**: XBRL 회사 사실 파일에서 재무 데이터를 파싱
- **계산 메트릭**:
  - 분기 EPS 성장률: (최근 분기 EPS / 4분기 전 EPS) - 1
  - 연간 EPS CAGR: ((최근 연간 EPS / 3년 전 EPS) ** (1/3)) - 1
  - 분기 수익 성장률: (최근 분기 수익 / 4분기 전 수익) - 1
  - 순이익률: 순이익 / 수익
  - ROE: 순이익 / 주주 자본
  - 부채 비율: 총 부채 / 주주 자본
- **XBRL 태그 예시**:
  - EPS: us-gaap:EarningsPerShareDiluted
  - 수익: us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax
  - 순이익: us-gaap:NetIncomeLoss
  - 자산: us-gaap:Assets
  - 부채: us-gaap:Liabilities
  - 주주 자본: us-gaap:StockholdersEquity
- **저장**: 계산된 데이터를 효율적인 액세스를 위해 Parquet 파일(companies.parquet)에 저장

**명령**: `python growth_stock_screener.py --mode parse`

### 4.3 스크리닝
**설명**: 파싱된 데이터를 기반으로 사용자 정의 기준에 따라 주식을 필터링하고 보고서를 생성합니다.

**세부 사항**:
- **데이터 로드**: companies.parquet 파일에서 데이터 읽기
- **재무 필터 적용**: JSON 설정 파일에 정의된 기준 적용
  - 예: 분기 EPS 성장률 ≥ 25%, ROE ≥ 15%
- **주가 성과 분석**: 
  - yfinance를 통해 필터링된 회사의 최근 6개월 주가 데이터 가져오기
  - S&P 500(티커: ^GSPC)의 동일 기간 성과와 비교
  - 조건: (주식 수익률 - S&P 500 수익률) > 0
- **선택적 기관 소유 필터**: 
  - SEC 13F filings 기반 기관 보유/증감 데이터 가져오기
  - 조건: 기관 소유 비율 또는 13F 기반 보유기관/축적 신호 기준 적용
- **보고서 생성**: 필터를 통과한 주식 목록을 CSV 파일로 출력
  - 포함 열: 티커, 회사명, 분기 EPS 성장률, 연간 EPS CAGR, 수익 성장률, 순이익률, ROE, 부채 비율, 주가 성과, (선택적) 기관 소유 비율

**명령**: `python growth_stock_screener.py --mode screen --config config.json`

## 비기능적 요구 사항
- **효율성**: 대량 데이터 처리를 위한 최적화(Parquet 파일 사용, 배치 처리 등)
- **견고성**: 누락된 데이터나 오류 발생 시 프로세스 중단 없이 진행
- **유지보수성**: 코드에 주석 및 문서화 포함, 모듈화된 구조로 설계
- **호환성**: Python 3.8 이상에서 실행 가능

## 사용자 인터페이스
- **형식**: 명령줄 인터페이스(CLI)
- **사용법**: 
  - `--mode download`: 데이터 다운로드
  - `--mode parse`: 데이터 파싱 및 저장
  - `--mode screen`: 스크리닝 실행
  - `--config <파일명>`: 설정 파일 경로 지정

- **설정 파일 예시** (config.json):
```json
{
  "criteria": {
    "quarterly_eps_growth": 0.25,
    "annual_eps_cagr": 0.25,
    "revenue_growth": 0.25,
    "profit_margin": 0.10,
    "roe": 0.15,
    "debt_to_equity": 1.0,
    "outperform_sp500": true,
    "institutional_ownership": 0.50
  },
  "output_path": "results.csv"
}
```

## 출력 형식
CSV 파일 열 예시:
```text
ticker,company_name,quarterly_eps_growth,annual_eps_cagr,revenue_growth,profit_margin,roe,debt_to_equity,sp500_outperformance,institutional_ownership
AAPL,Apple Inc.,0.30,0.28,0.27,0.22,0.25,0.8,0.05,0.65
```
설정: 사용자가 출력 열과 정렬 기준을 설정 파일에서 지정 가능

## 제약 사항
- SEC API는 재무 데이터 제공에 강점이 있지만, 주가 데이터와 기관 소유 비율은 별도 소스 필요
- 무료 데이터 소스의 정확성과 최신성에 의존
- 대량 데이터 처리로 인한 초기 실행 시간 증가 가능성

## 가정
- 사용자는 Python 및 CLI 사용에 익숙함
- 주기적으로 데이터를 업데이트하고 스크리닝을 실행할 의향 있음
- 데이터 검증은 사용자가 별도로 수행

## 위험 및 완화 방안
| 위험 | 완화 방안 |
| --- | --- |
| SEC API 형식 변경 | 오류 처리 및 로깅 강화, SEC 공지 모니터링 |
| 데이터 부정확성 | 사용자에게 결과 검증 권장, 데이터 체크 추가 |
| 대량 데이터로 인한 성능 저하 | 효율적인 파일 형식(Parquet) 및 배치 처리 |

## 결론
Growth Stock Screener는 SEC API를 핵심 데이터 소스로 활용하여, 성장 가능성이 높은 주식을 식별하려는 투자자들에게 강력한 도구를 제공합니다. yfinance와의 통합 및 선택적 외부 API 지원을 통해 CAN SLIM과 미너비니 전략의 핵심 요소를 반영하며, 사용자 친화적인 CLI와 커스터마이징 가능한 설정을 통해 유연성을 확보합니다. 이 PRD는 개발 과정에서 필요한 요구 사항과 고려 사항을 명확히 정의하여, 효율적이고 실용적인 애플리케이션 개발을 지원합니다.

이 PRD는 SEC API를 중심으로 한 구체적인 요구 사항을 반영하며, 사용자가 요청한 대로 완전하고 독립적인 문서로 작성되었습니다. 추가 수정이나 세부 사항이 필요하면 말씀해 주세요!