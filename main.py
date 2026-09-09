import datetime
import requests
import pandas as pd
import pytz
import streamlit as st


# -----------------------------------------------------------------------------
# 1. API 데이터 호출 및 캐싱 함수
# -----------------------------------------------------------------------------
# ttl=3600: 같은 날짜 데이터 요청 시 1시간(3600초) 동안은 API를 재요청하지 않고 캐시된 결과를 사용합니다.
@st.cache_data(ttl=3600)
def fetch_daily_boxoffice(target_date_str: str, api_key: str):
    """KOBIS API를 호출하여 일별 박스오피스 데이터를 가져오는 함수"""
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date_str}

    try:
        # KOBIS API 요청 (타임아웃 10초 설정)
        response = requests.get(url, params=params, timeout=10)
        # HTTP 오류 발생 시 예외 throw
        response.raise_for_status()
        data = response.json()
        return data, None
    except Exception as e:
        # 네트워크 오류 등 요청 실패 처리
        return None, f"네트워크 요청 중 오류가 발생했습니다: {str(e)}"


# -----------------------------------------------------------------------------
# 2. 메인 앱 레이아웃 및 로직
# -----------------------------------------------------------------------------
def main():
    st.set_page_config(
        page_title="어제 박스오피스 순위", page_icon="🎬", layout="wide"
    )

    st.title("🎬 어제의 박스오피스 순위")

    # [비밀 금고 설정 확인]
    # Streamlit Secrets(KOBIS_KEY) 존재 여부 검사
    if "KOBIS_KEY" not in st.secrets:
        st.error("🔑 API 키가 설정되지 않았습니다.")
        st.info(
            """
            **확인 방법:**
            1. Streamlit Cloud 설정(Secrets)에 `KOBIS_KEY = "발급받은_키"` 형태로 입력되어 있는지 확인하세요.
            2. 로컬에서 실행 중이라면 `.streamlit/secrets.toml` 파일에 키를 추가해야 합니다.
            """
        )
        return

    api_key = st.secrets["KOBIS_KEY"]

    # [한국 시간 기준 '어제' 날짜 계산]
    # 서버 시계와 상관없이 KST(Asia/Seoul) 기준 계산
    kst = pytz.timezone("Asia/Seoul")
    now_kst = datetime.datetime.now(kst)
    yesterday_kst = now_kst - datetime.timedelta(days=1)
    target_dt_str = yesterday_kst.strftime("%Y%m%d")  # YYYYMMDD 포맷
    formatted_date_display = yesterday_kst.strftime("%Y년 %m월 %d일")

    st.caption(f"기준 일자: {formatted_date_display} (한국 시간 기준)")

    # [API 데이터 로드]
    data, error_msg = fetch_daily_boxoffice(target_dt_str, api_key)

    # 1. 네트워크 요청 예외 처리
    if error_msg:
        st.error(error_msg)
        st.warning("인터넷 연결 상태나 KOBIS 서버 상태를 확인해 주세요.")
        return

    # 2. KOBIS 특유의 faultInfo 오류 응답 처리 (인증키 오류 등)
    if "faultInfo" in data:
        fault = data["faultInfo"]
        st.error(f"❌ KOBIS API 오류가 발생했습니다.")
        st.code(
            f"오류 코드: {fault.get('errorCode')}\n메시지: {fault.get('message')}"
        )
        st.info(
            """
            **확인 방법:**
            - Streamlit Secrets에 등록한 `KOBIS_KEY`가 올바른지 확인해 주세요.
            - KOBIS 개발자 센터에서 키 발급 상태 및 일일 사용량을 확인해 주세요.
            """
        )
        return

    # 3. 박스오피스 응답 데이터 구조 확인
    box_office_result = data.get("boxOfficeResult", {})
    daily_list = box_office_result.get("dailyBoxOfficeList", [])

    # 영화 목록이 비어있는 경우 처리
    if not daily_list:
        st.warning("⚠️ 해당 날짜의 박스오피스 데이터가 존재하지 않습니다.")
        st.info("KOBIS 집계 시각 지연 문제일 수 있으니 잠시 후 다시 시도해 주세요.")
        return

    # -----------------------------------------------------------------------------
    # 3. 데이터 가공 (문자열 -> 숫자 변환)
    # -----------------------------------------------------------------------------
    df = pd.DataFrame(daily_list)

    # 숫자 형태의 문자열 열을 실제 정수형(int)으로 변환
    numeric_cols = [
        "rank",
        "rankInten",
        "audiCnt",
        "audiAcc",
        "scrnCnt",
        "showCnt",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # 순위 기준 정렬
    df = df.sort_values(by="rank", ascending=True)

    # -----------------------------------------------------------------------------
    # 4. 화면 출력 (1위 영화 지표 카드 + 상위 5개 막대그래프 + 표)
    # -----------------------------------------------------------------------------
    # [1위 영화 핵심 지표 카드로 크게 보여주기]
    top_movie = df.iloc[0]
    st.subheader(f"🥇 1위: {top_movie['movieNm']}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="어제 관객수",
            value=f"{top_movie['audiCnt']:,} 명",
            delta=f"{top_movie['rankInten']:+d} 순위 변동"
            if top_movie["rankInten"] != 0
            else "순위 변동 없음",
        )
    with col2:
        st.metric(label="누적 관객수", value=f"{top_movie['audiAcc']:,} 명")
    with col3:
        st.metric(label="스크린수", value=f"{top_movie['scrnCnt']:,} 개")

    st.markdown("---")

    # [관객수 상위 5편 막대그래프]
    st.subheader("📊 관객수 상위 5개 영화")
    top5_df = df.head(5)[["movieNm", "audiCnt"]].set_index("movieNm")
    # Streamlit 기본 막대그래프 활용
    st.bar_chart(top5_df, y="audiCnt", color="#FF4B4B")

    st.markdown("---")

    # [전체 순위 표 출력]
    st.subheader("📋 전체 박스오피스 순위")

    # 표에 보여줄 컬럼 선택 및 이름 변경
    display_df = df[
        ["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]
    ].copy()
    display_df.columns = [
        "순위",
        "영화명",
        "개봉일",
        "어제 관객수",
        "누적 관객수",
        "스크린수",
    ]

    # 숫자에 쉼표(,) 포맷 적용하여 깔끔하게 표시
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "어제 관객수": st.column_config.NumberColumn(format="%d명"),
            "누적 관객수": st.column_config.NumberColumn(format="%d명"),
            "스크린수": st.column_config.NumberColumn(format="%d개"),
        },
    )


if __name__ == "__main__":
    main()
