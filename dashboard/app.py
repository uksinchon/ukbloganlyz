"""
Streamlit 웹 대시보드
- 실시간 블로그 분석 현황 시각화
- 인터랙티브 필터링 및 드릴다운
- 클라우드 배포 지원 (Streamlit Community Cloud)

실행: streamlit run dashboard/app.py
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# 프로젝트 루트 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from config.settings import DATA_DIR, OWN_BLOGS, COMPETITOR_BLOGS, ALL_BLOGS

# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="UK Centre - Blog Analysis Dashboard",
    page_icon="🇬🇧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 데이터 로드
# ============================================================
@st.cache_data(ttl=300)
def load_posts():
    posts_file = DATA_DIR / "posts.json"
    if posts_file.exists():
        with open(posts_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("posts", [])
    return []


@st.cache_data(ttl=300)
def load_latest_analysis():
    analysis_files = sorted(DATA_DIR.glob("analysis_*.json"), reverse=True)
    if analysis_files:
        with open(analysis_files[0], "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def posts_to_df(posts):
    if not posts:
        return pd.DataFrame()
    df = pd.DataFrame(posts)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "categories" in df.columns:
        df["main_category"] = df["categories"].apply(
            lambda x: x[0] if isinstance(x, list) and x else "미분류"
        )
    return df


# ============================================================
# 사이드바
# ============================================================
st.sidebar.title("🇬🇧 UK Centre")
st.sidebar.markdown("### 경쟁사 블로그 분석")
st.sidebar.markdown("---")

# 데이터 수집 버튼 (클라우드 환경용)
with st.sidebar.expander("🔄 데이터 수집", expanded=False):
    if st.button("📡 블로그 스크래핑 실행", use_container_width=True):
        with st.spinner("스크래핑 중... (1-2분 소요)"):
            try:
                from scraper.naver_blog_scraper import NaverBlogScraper
                scraper = NaverBlogScraper()
                posts = scraper.scrape_all_blogs()
                st.success(f"✅ {len(posts)}개 신규 포스트 수집!")
                st.cache_data.clear()
            except ImportError:
                st.error("스크래핑 모듈을 로드할 수 없습니다. 로컬 서버에서 실행해주세요.")
            except Exception as e:
                st.error(f"스크래핑 실패: {e}")

    if st.button("📊 분석 실행", use_container_width=True):
        with st.spinner("분석 중..."):
            try:
                from scraper.naver_blog_scraper import NaverBlogScraper
                from analyzer.trend_analyzer import TrendAnalyzer
                scraper = NaverBlogScraper()
                recent = scraper.get_recent_posts(days=30)
                analyzer = TrendAnalyzer(recent)
                analysis = analyzer.generate_full_analysis("최근 30일")
                st.success(f"✅ {len(recent)}개 포스트 분석 완료!")
                st.cache_data.clear()
            except ImportError:
                st.error("분석 모듈을 로드할 수 없습니다. 로컬 서버에서 실행해주세요.")
            except Exception as e:
                st.error(f"분석 실패: {e}")

st.sidebar.markdown("---")

# 날짜 필터
date_range = st.sidebar.selectbox(
    "📅 분석 기간",
    ["최근 1일", "최근 7일", "최근 30일", "최근 90일", "전체"],
    index=2,
)

date_map = {
    "최근 1일": 1, "최근 7일": 7, "최근 30일": 30,
    "최근 90일": 90, "전체": 9999,
}
days = date_map[date_range]

# 블로그 필터
blog_filter = st.sidebar.multiselect(
    "🏢 블로그 선택",
    options=list(ALL_BLOGS.keys()),
    default=list(ALL_BLOGS.keys()),
)
selected_blog_ids = {ALL_BLOGS[name] for name in blog_filter}

# ============================================================
# 데이터 준비
# ============================================================
posts = load_posts()
df = posts_to_df(posts)
analysis = load_latest_analysis()

if not df.empty:
    cutoff = datetime.now() - timedelta(days=days)
    df = df[df["date"] >= cutoff] if "date" in df.columns else df
    df = df[df["blog_id"].isin(selected_blog_ids)] if "blog_id" in df.columns else df

# ============================================================
# 메인 대시보드
# ============================================================
st.title("📊 경쟁사 블로그 분석 대시보드")

last_updated = "없음"
posts_file = DATA_DIR / "posts.json"
if posts_file.exists():
    with open(posts_file, "r", encoding="utf-8") as f:
        meta = json.load(f)
        last_updated = meta.get("last_updated", "없음")
        if last_updated and last_updated != "없음":
            try:
                dt = datetime.fromisoformat(last_updated)
                last_updated = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass

st.markdown(f"**분석 기간**: {date_range} | **마지막 업데이트**: {last_updated}")

if df.empty:
    st.warning("⚠️ 데이터가 없습니다.")
    st.info("""
    **시작하는 방법:**
    1. 왼쪽 사이드바의 '🔄 데이터 수집' → '📡 블로그 스크래핑 실행' 클릭
    2. 또는 터미널에서: `python main.py scrape`
    3. 스크래핑 완료 후 이 페이지를 새로고침하세요
    """)
    st.stop()

# ---- KPI 카드 ----
own_ids = set(OWN_BLOGS.values())
col1, col2, col3, col4 = st.columns(4)
col1.metric("전체 포스트", f"{len(df)}건")
col2.metric("본사 포스트", f"{len(df[df['blog_id'].isin(own_ids)])}건")
col3.metric("경쟁사 포스트", f"{len(df[~df['blog_id'].isin(own_ids)])}건")
col4.metric("활성 블로그", f"{df['blog_id'].nunique()}개")

st.markdown("---")

# ---- 탭 구성 ----
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 포스팅 트렌드", "🏢 블로그별 현황", "🏷️ 주제별 분석",
    "⚔️ 본사 vs 경쟁사", "🤖 AI 인사이트",
])

# ---- Tab 1: 포스팅 트렌드 ----
with tab1:
    st.subheader("일별 포스팅 트렌드")
    if "date" in df.columns:
        daily = df.groupby(df["date"].dt.date).size().reset_index(name="count")
        daily.columns = ["date", "count"]
        fig = px.line(daily, x="date", y="count", title="일별 포스팅 추이",
                     markers=True)
        fig.update_traces(line_color="#1976D2")
        fig.update_layout(xaxis_title="날짜", yaxis_title="포스트 수")
        st.plotly_chart(fig, use_container_width=True)

        # 본사 vs 경쟁사 트렌드
        df_trend = df.copy()
        df_trend["is_own"] = df_trend["blog_id"].isin(own_ids)
        df_trend["group"] = df_trend["is_own"].map({True: "🔵 UK Centre (본사)", False: "🔴 경쟁사"})
        group_daily = df_trend.groupby([df_trend["date"].dt.date, "group"]).size().reset_index(name="count")
        group_daily.columns = ["date", "group", "count"]
        fig2 = px.bar(group_daily, x="date", y="count", color="group",
                      title="본사 vs 경쟁사 일별 포스팅 비교",
                      color_discrete_map={"🔵 UK Centre (본사)": "#1976D2", "🔴 경쟁사": "#FF7043"})
        fig2.update_layout(xaxis_title="날짜", yaxis_title="포스트 수", barmode="group")
        st.plotly_chart(fig2, use_container_width=True)

# ---- Tab 2: 블로그별 현황 ----
with tab2:
    st.subheader("블로그별 포스팅 수")
    blog_counts = df.groupby("blog_name").size().reset_index(name="count").sort_values("count", ascending=True)

    # 본사/경쟁사 구분 색상
    blog_counts["type"] = blog_counts["blog_name"].apply(
        lambda x: "🔵 본사" if any(x.startswith("UK유학센터") for _ in [1]) else "🔴 경쟁사"
    )
    fig = px.bar(blog_counts, x="count", y="blog_name", orientation="h",
                 title="블로그별 포스팅 수", color="type",
                 color_discrete_map={"🔵 본사": "#1976D2", "🔴 경쟁사": "#FF7043"})
    fig.update_layout(yaxis_title="", xaxis_title="포스트 수")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📋 최근 포스트 목록")
    recent = df.sort_values("date", ascending=False).head(30)
    display_cols = ["date", "blog_name", "title"]
    if "url" in recent.columns:
        display_cols.append("url")
    st.dataframe(
        recent[display_cols].reset_index(drop=True),
        use_container_width=True,
        column_config={
            "date": st.column_config.DateColumn("날짜"),
            "blog_name": st.column_config.TextColumn("블로그"),
            "title": st.column_config.TextColumn("제목", width="large"),
            "url": st.column_config.LinkColumn("링크"),
        },
    )

# ---- Tab 3: 주제별 분석 ----
with tab3:
    st.subheader("주제별 포스팅 분포")
    if "main_category" in df.columns:
        cat_counts = df["main_category"].value_counts().reset_index()
        cat_counts.columns = ["category", "count"]

        col_a, col_b = st.columns(2)
        with col_a:
            fig = px.pie(cat_counts, values="count", names="category",
                         title="주제 분포 (파이차트)", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            fig = px.bar(cat_counts.sort_values("count", ascending=True),
                        x="count", y="category", orientation="h",
                        title="주제별 포스트 수", color="count",
                        color_continuous_scale="Blues")
            fig.update_layout(yaxis_title="", xaxis_title="포스트 수")
            st.plotly_chart(fig, use_container_width=True)

        # 주제별 블로그 히트맵
        st.subheader("🗺️ 블로그 x 주제 히트맵")
        if "blog_name" in df.columns:
            cross = pd.crosstab(df["blog_name"], df["main_category"])
            fig = px.imshow(cross, text_auto=True, title="어떤 블로그가 어떤 주제를 다루는지",
                          color_continuous_scale="YlOrRd", aspect="auto")
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)

# ---- Tab 4: 본사 vs 경쟁사 ----
with tab4:
    st.subheader("⚔️ 본사 vs 경쟁사 비교")

    if "main_category" in df.columns:
        own_df = df[df["blog_id"].isin(own_ids)]
        comp_df = df[~df["blog_id"].isin(own_ids)]

        own_cats = own_df["main_category"].value_counts().to_dict()
        comp_cats = comp_df["main_category"].value_counts().to_dict()

        all_cats = sorted(set(list(own_cats.keys()) + list(comp_cats.keys())))
        comparison_df = pd.DataFrame({
            "주제": all_cats,
            "UK Centre (본사)": [own_cats.get(c, 0) for c in all_cats],
            "경쟁사": [comp_cats.get(c, 0) for c in all_cats],
        })

        fig = go.Figure()
        fig.add_trace(go.Bar(name="UK Centre (본사)", x=comparison_df["주제"],
                            y=comparison_df["UK Centre (본사)"], marker_color="#1976D2"))
        fig.add_trace(go.Bar(name="경쟁사", x=comparison_df["주제"],
                            y=comparison_df["경쟁사"], marker_color="#FF7043"))
        fig.update_layout(barmode="group", title="주제별 포스팅 비교",
                         xaxis_title="주제", yaxis_title="포스트 수")
        st.plotly_chart(fig, use_container_width=True)

        # 놓치는 주제 경고
        st.subheader("🚨 놓치고 있는 주제 (Action Required)")
        missed = []
        for cat in all_cats:
            own_count = own_cats.get(cat, 0)
            comp_count = comp_cats.get(cat, 0)
            if comp_count > 0 and own_count == 0:
                missed.append({
                    "주제": cat,
                    "경쟁사 포스트 수": comp_count,
                    "본사 포스트 수": own_count,
                    "상태": "🔴 미다룸",
                    "권장 조치": "즉시 관련 콘텐츠 작성 필요",
                })
            elif comp_count > own_count * 2 and comp_count > 2:
                missed.append({
                    "주제": cat,
                    "경쟁사 포스트 수": comp_count,
                    "본사 포스트 수": own_count,
                    "상태": "🟡 부족",
                    "권장 조치": "포스팅 빈도 증가 필요",
                })

        if missed:
            st.error(f"⚠️ {len(missed)}개 주제에서 경쟁사 대비 뒤처지고 있습니다!")
            st.dataframe(pd.DataFrame(missed), use_container_width=True, hide_index=True)
        else:
            st.success("✅ 현재 주요 트렌드를 놓치지 않고 있습니다!")

        # 주제 커버리지 비율
        st.subheader("📊 주제 커버리지 비율")
        coverage = []
        for cat in all_cats:
            own_c = own_cats.get(cat, 0)
            comp_c = comp_cats.get(cat, 0)
            total = own_c + comp_c
            if total > 0:
                own_pct = own_c / total * 100
                coverage.append({"주제": cat, "본사 비율": own_pct, "경쟁사 비율": 100 - own_pct})

        if coverage:
            cov_df = pd.DataFrame(coverage)
            fig = go.Figure()
            fig.add_trace(go.Bar(name="본사", x=cov_df["주제"], y=cov_df["본사 비율"],
                                marker_color="#1976D2"))
            fig.add_trace(go.Bar(name="경쟁사", x=cov_df["주제"], y=cov_df["경쟁사 비율"],
                                marker_color="#FF7043"))
            fig.update_layout(barmode="stack", title="주제별 본사 vs 경쟁사 비율 (%)",
                            yaxis_title="비율 (%)")
            st.plotly_chart(fig, use_container_width=True)

# ---- Tab 5: AI 인사이트 ----
with tab5:
    st.subheader("🤖 AI 심층 분석")
    if analysis and analysis.get("ai_analysis"):
        st.markdown(analysis["ai_analysis"])
    else:
        st.info("AI 분석 결과가 없습니다. ANTHROPIC_API_KEY를 설정하고 '📊 분석 실행' 버튼을 클릭해주세요.")

    st.markdown("---")

    if analysis:
        st.subheader("📋 최근 분석 요약")
        col_x, col_y, col_z = st.columns(3)
        col_x.metric("분석 기간", analysis.get("period", "-"))
        col_y.metric("총 포스트", f"{analysis.get('total_posts', 0)}건")
        col_z.metric("생성 시각", analysis.get("generated_at", "-")[:16] if analysis.get("generated_at") else "-")

    # 상위 키워드
    if analysis and analysis.get("top_keywords"):
        st.subheader("🔑 상위 키워드")
        kw_data = analysis["top_keywords"][:15]
        kw_df = pd.DataFrame(kw_data, columns=["키워드", "빈도"])
        fig = px.bar(kw_df.sort_values("빈도", ascending=True),
                    x="빈도", y="키워드", orientation="h",
                    title="가장 많이 사용된 키워드 TOP 15",
                    color="빈도", color_continuous_scale="Purples")
        st.plotly_chart(fig, use_container_width=True)

# ---- 사이드바 하단 ----
st.sidebar.markdown("---")

# PDF 다운로드
st.sidebar.markdown("### 📥 리포트 다운로드")
report_dir = PROJECT_ROOT / "reports" / "output"
if report_dir.exists():
    report_files = sorted(report_dir.glob("*.pdf"), reverse=True)
    if report_files:
        latest_report = report_files[0]
        with open(latest_report, "rb") as f:
            st.sidebar.download_button(
                label="📄 최신 PDF 리포트 다운로드",
                data=f.read(),
                file_name=latest_report.name,
                mime="application/pdf",
                use_container_width=True,
            )
    else:
        st.sidebar.info("PDF 리포트가 아직 없습니다.")
else:
    st.sidebar.info("리포트 폴더가 없습니다.")

st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 모니터링 대상")
st.sidebar.markdown(f"**본사**: {len(OWN_BLOGS)}개 블로그")
st.sidebar.markdown(f"**경쟁사**: {len(COMPETITOR_BLOGS)}개 블로그")
st.sidebar.markdown(f"**총**: {len(ALL_BLOGS)}개 블로그")

st.sidebar.markdown("---")
st.sidebar.caption("UK Centre Blog Analysis System v1.0")
st.sidebar.caption(f"Data: {len(posts)} posts loaded")
