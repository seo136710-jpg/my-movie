import datetime
import requests
import pandas as pd
import pytz
import streamlit as st


# -----------------------------------------------------------------------------
# 1. API 데이터 호출 및 캐싱 함수
# -----------------------------------------------------------------------------
# ttl=3600: 선택한 날짜에 대한 요청 결과를 1시간(3600초) 동안 저장하여 재요청을 방지합니다.
@st.cache_data(ttl=3600)
def fetch_daily_boxoffice(target_date_str: str, api_key: str):
    """KOBIS API를 호출하여 일별 박스오피스 데이터를 가져오는 함수"""
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {"key": api_key, "targetDt": target_date_str}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data, None
    except Exception as e:
        return None, f"네트워크 요청 중 오류가 발생했습니다: {str(e)}"


# -----------------------------------------------------------------------------
# 2. 메인 앱 레이아웃 및 로직
# -----------------------------------------------------------------------------
def main():
    st.set_page_config(
        page_title="일별 박스오피스 조회", page_icon="🎬", layout="wide"
    )

    st.title("🎬 일별 박스오피스 조회")

    # [비밀 금고 설정 확인]
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

    # [한국 시간 기준 날짜 범위를 계산]
    kst = pytz.timezone("Asia/Seoul")
    now_kst = datetime.datetime.now(kst).date()
    yesterday_kst = now_kst - datetime.timedelta(days=1)

    # [달력에서 날짜 선택하기]
    # 선택 가능한 최대 날짜(max_value)는 한국 시간 기준 '어제'로 제한합니다.
    selected_date = st.date_input(
        "조회할 날짜를 선택하세요",
        value=yesterday_kst,
        max_value=yesterday_kst,
        help="오늘 데이터는 아직 집계 전이므로 어제 날짜까지 선택할 수 있습니다.",
    )

    # 선택된 날짜를 API에 전달할 YYYYMMDD 포맷 문자열로 변환
    target_dt_str = selected_date.strftime("%Y%m%d")
    formatted_date_display = selected_date.strftime("%Y년 %m월 %d일")

    st.caption(f"조회 일자: {formatted_date_display}")

    # [API 데이터 로드]
    data, error_msg = fetch_daily_boxoffice(target_dt_str, api_key)

    # 1. 네트워크 요청 오류 처리
    if error_msg:
        st.error(error_msg)
        st.warning("인터넷 연결 상태나 KOBIS 서버 상태를 확인해 주세요.")
        return

    # 2. KOBIS faultInfo 오류 응답 처리 (인증키 오류 등)
    if "faultInfo" in data:
        fault = data["faultInfo"]
        st.error("❌ KOBIS API 오류가 발생했습니다.")
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
        st.warning("⚠️ 그날은 아직 집계 전입니다.")
        return

    # -----------------------------------------------------------------------------
    # 3. 데이터 가공 및 변환
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

    # [데이터 가공 1: 순위 증감 화살표 문자열 생성]
    def format_rank_change(change):
        if change > 0:
            return f"🔺 {change}"  # 오른 영화 (빨간 위 화살표)
        elif change < 0:
            return f"🔹 {abs(change)}"  # 내린 영화 (파란 아래 화살표)
        else:
            return "-"

    df["순위변동"] = df["rankInten"].apply(format_rank_change)

    # [데이터 가공 2: 누적관객 100만 이상 영화 이름에 트로피 🏆 이모지 추가]
    def add_trophy(row):
        name = row["movieNm"]
        if row["audiAcc"] >= 1000000:
            return f"🏆 {name}"
        return name

    df["표시영화명"] = df.apply(add_trophy, axis=1)

    # -----------------------------------------------------------------------------
    # 4. 화면 출력 (1위 영화 카드 + 상위 5개 막대그래프 + 표)
    # -----------------------------------------------------------------------------
    # [1위 영화 핵심 지표 카드로 표시]
    top_movie = df.iloc[0]
    st.subheader(f"🥇 1위: {top_movie['표시영화명']}")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="당일 관객수",
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
    st.bar_chart(top5_df, y="audiCnt", color="#FF4B4B")

    st.markdown("---")

    # [전체 순위 표 출력]
    st.subheader("📋 전체 박스오피스 순위")

    display_df = df[
        [
            "rank",
            "순위변동",
            "표시영화명",
            "openDt",
            "audiCnt",
            "audiAcc",
            "scrnCnt",
        ]
    ].copy()
    display_df.columns = [
        "순위",
        "순위 변동",
        "영화명",
        "개봉일",
        "당일 관객수",
        "누적 관객수",
        "스크린수",
    ]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "당일 관객수": st.column_config.NumberColumn(format="%d명"),
            "누적 관객수": st.column_config.NumberColumn(format="%d명"),
            "스크린수": st.column_config.NumberColumn(format="%d개"),
        },
    )


if __name__ == "__main__":
    main()
