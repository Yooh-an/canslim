#!/usr/bin/env python3
"""
Test Parser Script

이 스크립트는 특정 파라미터로 facts parser를 실행하여 디버깅합니다.
"""

import os
import sys
import json
import pandas as pd
import logging
from pathlib import Path
import argparse

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# 로거 설정
try:
    from src.utils.logger import setup_logger
    logger = setup_logger("test_parser", level=logging.DEBUG)  # log_level 대신 level 사용
except ImportError:
    import logging
    logger = logging.getLogger("test_parser")
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

from src.parsers.facts_parser import XBRLFactsParser

def load_config(config_path="config/config.json"):
    """설정 파일 로드"""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"설정 파일 로드 오류: {e}")
        sys.exit(1)

def test_company(config, cik=None, ticker=None):
    """특정 회사에 대해 파서 테스트 실행"""
    # 파서 초기화
    facts_parser = XBRLFactsParser(config)
    
    # CIK로 파일 찾기
    if cik:
        # CIK 형식 처리 (10자리 패딩)
        cik_padded = str(cik).zfill(10)
        file_path = os.path.join(config['data_paths']['company_facts_dir'], f"CIK{cik_padded}.json")
        
        if not os.path.exists(file_path):
            logger.error(f"파일을 찾을 수 없음: {file_path}")
            return
        
        logger.info(f"파일 처리 중: {file_path}")
        
        # 단일 파일 처리
        metrics = facts_parser.process_company_file(file_path)
        
        # 결과 출력
        print("\n== 처리 결과 ==")
        print(f"CIK: {metrics.get('cik')}")
        print(f"회사명: {metrics.get('name')}")
        print(f"티커: {metrics.get('ticker')}")
        
        # 재무 지표 출력
        financial_metrics = [
            ('quarterly_eps_growth', '분기별 EPS 성장률'), 
            ('annual_eps_cagr', '연간 EPS CAGR'),
            ('revenue_growth', '매출 성장률'),
            ('profit_margin', '이익률'),
            ('roe', 'ROE'),
            ('debt_to_equity', '부채비율')
        ]
        
        print("\n== 재무 지표 ==")
        for key, label in financial_metrics:
            value = metrics.get(key)
            if value is not None:
                if key in ['quarterly_eps_growth', 'annual_eps_cagr', 'revenue_growth', 'profit_margin', 'roe']:
                    print(f"{label}: {value*100:.2f}%")
                else:
                    print(f"{label}: {value:.2f}")
            else:
                print(f"{label}: 데이터 없음")
        
        # 원본 파일 내용 분석
        print("\n== 원본 XBRL 데이터 분석 ==")
        analyze_facts_file(file_path)
        
    # 티커로 CIK 찾기
    elif ticker:
        # 매핑 파일 로드
        mapping_file = os.path.join(config["data_paths"].get("processed_data_dir", "data/processed"), 
                                  "cik_ticker_mapping.csv")
        
        if os.path.exists(mapping_file):
            try:
                df = pd.read_csv(mapping_file)
                ticker = ticker.lower()  # 대소문자 구분 없이 검색
                
                # 티커로 검색
                match = df[df['ticker'].str.lower() == ticker]
                
                if not match.empty:
                    cik = str(match.iloc[0]['cik']).zfill(10)
                    print(f"티커 {ticker}에 대한 CIK를 찾음: {cik}")
                    # 찾은 CIK로 테스트
                    test_company(config, cik=cik)
                    return
                else:
                    logger.error(f"티커 {ticker}에 대한 CIK를 찾을 수 없음")
                    return
                    
            except Exception as e:
                logger.error(f"매핑 파일 처리 오류: {e}")
        else:
            logger.error(f"매핑 파일을 찾을 수 없음: {mapping_file}")
            
            # 매핑 파일이 없으면 직접 회사 디렉터리 검색
            print("CIK-티커 매핑 파일을 찾을 수 없습니다. 회사 파일 직접 검색 중...")
            
            # 회사 파일 검색
            company_facts_dir = config['data_paths']['company_facts_dir']
            files = os.listdir(company_facts_dir)
            
            for filename in files:
                if not filename.startswith("CIK") or not filename.endswith(".json"):
                    continue
                
                file_path = os.path.join(company_facts_dir, filename)
                
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                    
                    # 티커 매칭
                    tickers = data.get("tickers", [])
                    if isinstance(tickers, list) and tickers:
                        if ticker.lower() in [t.lower() for t in tickers]:
                            print(f"티커 {ticker}에 대한 파일을 찾음: {filename}")
                            cik = filename.replace("CIK", "").replace(".json", "")
                            # 찾은 CIK로 테스트
                            test_company(config, cik=cik)
                            return
                    elif isinstance(tickers, str) and tickers.lower() == ticker.lower():
                        print(f"티커 {ticker}에 대한 파일을 찾음: {filename}")
                        cik = filename.replace("CIK", "").replace(".json", "")
                        # 찾은 CIK로 테스트
                        test_company(config, cik=cik)
                        return
                
                except Exception:
                    continue
            
            logger.error(f"티커 {ticker}에 대한 파일을 찾을 수 없음")

def analyze_facts_file(file_path):
    """XBRL 파일의 내용을 자세히 분석"""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # 기본 정보
        print(f"엔티티명: {data.get('entityName', '정보 없음')}")
        print(f"티커: {data.get('tickers', '정보 없음')}")
        
        # facts 구조 확인
        if "facts" not in data:
            print("오류: 'facts' 키가 없습니다")
            return
        
        facts = data["facts"]
        
        # us-gaap 네임스페이스 확인
        if "us-gaap" not in facts:
            print("오류: 'us-gaap' 네임스페이스가 없습니다")
            print(f"사용 가능한 네임스페이스: {list(facts.keys())}")
            return
        
        us_gaap = facts["us-gaap"]
        
        # 주요 재무 태그 확인
        key_tags = {
            "EPS": ["EarningsPerShareDiluted", "EarningsPerShareBasic", "IncomeLossPerShareBasicAndDiluted"],
            "매출": ["Revenue", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax"],
            "순이익": ["NetIncomeLoss", "ProfitLoss", "NetIncome"],
            "자산": ["Assets"],
            "부채": ["Liabilities"],
            "자본": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"]
        }
        
        print("\n== 주요 재무 태그 확인 ==")
        for category, tags in key_tags.items():
            print(f"\n{category} 관련 태그:")
            found = False
            
            for tag in tags:
                if tag in us_gaap:
                    print(f"  ✓ {tag} 태그 발견")
                    found = True
                    
                    # 단위 확인
                    units = us_gaap[tag].get("units", {})
                    if units:
                        print(f"    단위: {list(units.keys())}")
                        
                        # 값 예시 표시
                        for unit, values in units.items():
                            if values:
                                # 최신 값만 표시
                                for value in values[:3]:
                                    if "form" in value and "period" in value:
                                        form = value.get("form", "")
                                        end_date = value.get("period", {}).get("endDate", "")
                                        val = value.get("val", "")
                                        print(f"    {end_date} ({form}): {val} {unit}")
                    else:
                        print("    유효한 단위 없음")
                    
            if not found:
                print(f"  ✗ 관련 태그 없음")
        
        # 사용 가능한 모든 태그 수
        print(f"\n총 {len(us_gaap)} us-gaap 태그 사용 가능")
        
        # 샘플 태그 10개 표시
        print("\n== 샘플 태그 목록 ==")
        for i, tag in enumerate(list(us_gaap.keys())[:10]):
            print(f"{i+1}. {tag}")
        
    except Exception as e:
        print(f"파일 분석 오류: {e}")
        import traceback
        traceback.print_exc()

def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description="재무 데이터 파서 테스트")
    parser.add_argument("--config", default="config/config.json", help="설정 파일 경로")
    parser.add_argument("--cik", help="테스트할 회사의 CIK 번호")
    parser.add_argument("--ticker", help="테스트할 회사의 티커 심볼")
    parser.add_argument("--process-all", action="store_true", help="모든 회사 처리")
    
    args = parser.parse_args()
    
    # 설정 로드
    config = load_config(args.config)
    
    if args.cik:
        test_company(config, cik=args.cik)
    elif args.ticker:
        test_company(config, ticker=args.ticker)
    elif args.process_all:
        # 전체 파일 처리 테스트
        facts_parser = XBRLFactsParser(config)
        metrics_df = facts_parser.process_all(force=True)
        
        # 결과 요약
        print(f"\n처리된 회사 수: {len(metrics_df)}")
        print(f"사용 가능한 컬럼: {metrics_df.columns.tolist()}")
        
        # 지표별 통계
        for col in ['quarterly_eps_growth', 'annual_eps_cagr', 'revenue_growth', 
                   'profit_margin', 'roe', 'debt_to_equity']:
            if col in metrics_df.columns:
                count = metrics_df[col].notnull().sum()
                print(f"{col}: {count} 회사에 값 있음 ({count/len(metrics_df)*100:.1f}%)")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
