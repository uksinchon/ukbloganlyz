"""
UK Centre 경쟁사 블로그 분석 대시보드 v2.0
- 신촌지사 vs 본사 vs 경쟁사 구조
- 블로그별 개별 포스팅 현황판
- 경쟁사 실시간 추가 기능
- AI 리포트 + Word/PDF 내보내기

실행: streamlit run dashboard/app.py
"""
import json
import sys
import io
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

# 프로젝트 루트 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from config.settings import (
    DATA_DIR, SINCHON_BLOGS, HQ_BLOGS, OWN_BLOGS,
    COMPETITOR_BLOGS, ALL_BLOGS, CUSTOM_COMPETITORS_FILE,
)

# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="UK Centre - 경쟁사 블로그 분석",
    page_icon="🇬🇧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 사용자 추가 경쟁사 관리
# ============================================================
def load_custom_competitors() -> dict:
    if CUSTOM_COMPETITORS_FILE.exists():
        with open(CUSTOM_COMPETITORS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_custom_competitors(data: dict):
    with open(CUSTOM_COMPETITORS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_all_blogs() -> dict:
    """고정 블로그 + 사용자 추가 블로그"""
    custom = load_custom_competitors()
    return {**ALL_BLOGS, **custom}

def get_blog_group(blog_id: str) -> str:
    """블로그의 소속 그룹 반환"""
    if blog_id in SINCHON_BLOGS.values():
        return "🔵 신촌지사"
    elif blog_id in HQ_BLOGS.values():
        return "🟢 본사"
    else:
        return "🔴 경쟁사"

def get_blog_color(blog_id: str) -> str:
    if blog_id in SINCHON_BLOGS.values():
        return "#1565C0"
    elif blog_id in HQ_BLOGS.values():
        return "#2E7D32"
    else:
        return "#E53935"

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
st.sidebar.markdown("**경쟁사 블로그 분석 시스템**")
st.sidebar.markdown("---")

# ---- 경쟁사 추가 기능 ----
st.sidebar.markdown("### ➕ 경쟁사 블로그 추가")
with st.sidebar.form("add_competitor", clear_on_submit=True):
    new_name = st.text_input("업체명", placeholder="예: 새로운유학원")
    new_url = st.text_input("네이버 블로그 URL", placeholder="https://blog.naver.com/blogid")
    submitted = st.form_submit_button("추가", use_container_width=True)
    if submitted and new_name and new_url:
        # URL에서 blog_id 추출
        blog_id = new_url.rstrip("/").split("/")[-1]
        if blog_id:
            custom = load_custom_competitors()
            custom[new_name] = blog_id
            save_custom_competitors(custom)
            st.success(f"✅ '{new_name}' 추가 완료!")
            st.cache_data.clear()
        else:
            st.error("올바른 네이버 블로그 URL을 입력해주세요.")

# 추가된 경쟁사 목록
custom_comps = load_custom_competitors()
if custom_comps:
    with st.sidebar.expander(f"📋 추가된 경쟁사 ({len(custom_comps)}개)"):
        for name, bid in custom_comps.items():
            col_a, col_b = st.columns([3, 1])
            col_a.caption(f"{name} ({bid})")
            if col_b.button("❌", key=f"del_{bid}"):
                custom_comps.pop(name)
                save_custom_competitors(custom_comps)
                st.cache_data.clear()
                st.rerun()

st.sidebar.markdown("---")

# ---- 기간 필터 ----
st.sidebar.markdown("### 📅 분석 기간")
period = st.sidebar.radio(
    "기간 선택",
    ["당일", "최근 1주일", "최근 한달"],
    index=1,
    horizontal=True,
)
period_days = {"당일": 1, "최근 1주일": 7, "최근 한달": 30}[period]

# ---- 데이터 수집 ----
with st.sidebar.expander("🔄 데이터 수집"):
    if st.button("📡 스크래핑 실행", use_container_width=True):
        progress_area = st.empty()
        try:
            from scraper.naver_blog_scraper import NaverBlogScraper
            scraper = NaverBlogScraper()
            scraper.on_progress = lambda msg: progress_area.caption(msg)
            posts = scraper.scrape_all_blogs()
            progress_area.empty()
            st.success(f"✅ {len(posts)}개 수집!")
            st.cache_data.clear()
        except Exception as e:
            progress_area.empty()
            st.error(f"실패: {e}")

# ============================================================
# 데이터 준비
# ============================================================
all_blogs = get_all_blogs()
blog_name_map = {v: k for k, v in all_blogs.items()}

posts = load_posts()
df = posts_to_df(posts)
analysis = load_latest_analysis()

if not df.empty:
    cutoff = datetime.now() - timedelta(days=period_days)
    if "date" in df.columns:
        df = df[df["date"] >= cutoff]

# ============================================================
# 메인 대시보드 헤더
# ============================================================
st.markdown("""
<div style="background: linear-gradient(135deg, #1a237e 0%, #283593 100%);
            padding: 25px 30px; border-radius: 12px; margin-bottom: 20px;">
    <h1 style="color: white; margin: 0; font-size: 28px;">
        🇬🇧 영국유학센터 경쟁사 블로그 분석 대시보드
    </h1>
    <p style="color: #B3C5FF; margin: 5px 0 0 0; font-size: 14px;">
        신촌지사 vs 본사 vs 경쟁사 — 포스팅 현황을 한눈에 파악하여 전략적 우위를 점하기 위한 대시보드
    </p>
</div>
""", unsafe_allow_html=True)

# 모니터링 대상 요약
col_info1, col_info2, col_info3, col_info4 = st.columns(4)
col_info1.markdown(f"**🔵 신촌지사** {len(SINCHON_BLOGS)}개")
col_info2.markdown(f"**🟢 본사** {len(HQ_BLOGS)}개")
col_info3.markdown(f"**🔴 경쟁사** {len(COMPETITOR_BLOGS) + len(custom_comps)}개")
col_info4.markdown(f"**📅 기간** {period}")

if df.empty:
    st.warning("⚠️ 데이터가 없습니다. 사이드바 '🔄 데이터 수집' → '📡 스크래핑 실행'을 클릭하세요.")
    st.stop()

st.markdown("---")

# ============================================================
# 탭 구성
# ============================================================
tab1, tab2, tab3, tab4 = st.tabs([
    "📈 일별 포스팅 트렌드",
    "🏢 블로그별 개별 현황판",
    "🏷️ 주제별 분석",
    "🤖 AI 리포트",
])

# ============================================================
# Tab 1: 일별 포스팅 트렌드
# ============================================================
with tab1:
    st.subheader("📈 일별 포스팅 트렌드 (Daily Tracking)")
    st.caption("각 업체 블로그별 일일 포스팅 수를 한눈에 비교합니다")

    if "date" in df.columns and "blog_name" in df.columns:
        # 블로그별 일별 포스팅 수
        daily_by_blog = df.groupby([df["date"].dt.date, "blog_name"]).size().reset_index(name="count")
        daily_by_blog.columns = ["date", "blog_name", "count"]

        # 그룹 색상
        daily_by_blog["group"] = daily_by_blog["blog_name"].apply(
            lambda x: get_blog_group(all_blogs.get(x, ""))
        )

        # 전체 트렌드 (블로그별 라인)
        fig = px.line(
            daily_by_blog, x="date", y="count", color="blog_name",
            title=f"블로그별 일별 포스팅 수 ({period})",
            markers=True,
        )
        fig.update_layout(
            xaxis_title="날짜", yaxis_title="포스트 수",
            legend_title="블로그",
            height=500,
        )
        st.plotly_chart(fig, use_container_width=True)

        # ---- 3그룹 비교 바 차트 ----
        st.subheader("🔵 신촌지사 vs 🟢 본사 vs 🔴 경쟁사")

        sinchon_ids = set(SINCHON_BLOGS.values())
        hq_ids = set(HQ_BLOGS.values())
        own_ids = set(OWN_BLOGS.values())

        df_chart = df.copy()
        def assign_group(bid):
            if bid in sinchon_ids:
                return "🔵 신촌지사"
            elif bid in hq_ids:
                return "🟢 본사"
            else:
                return "🔴 경쟁사"
        df_chart["group"] = df_chart["blog_id"].apply(assign_group)

        group_daily = df_chart.groupby([df_chart["date"].dt.date, "group"]).size().reset_index(name="count")
        group_daily.columns = ["date", "group", "count"]

        fig2 = px.bar(
            group_daily, x="date", y="count", color="group",
            title="3그룹 일별 포스팅 비교",
            color_discrete_map={
                "🔵 신촌지사": "#1565C0",
                "🟢 본사": "#2E7D32",
                "🔴 경쟁사": "#E53935",
            },
            barmode="group",
        )
        fig2.update_layout(xaxis_title="날짜", yaxis_title="포스트 수", height=400)
        st.plotly_chart(fig2, use_container_width=True)

        # ---- 기간 총합 요약 테이블 ----
        st.subheader(f"📊 {period} 포스팅 수 총합")
        blog_totals = df.groupby("blog_name").size().reset_index(name="포스트 수")
        blog_totals["blog_id"] = blog_totals["blog_name"].map({v: k for v, k in zip(
            [all_blogs.get(n, "") for n in blog_totals["blog_name"]], blog_totals["blog_name"]
        )})
        blog_totals["그룹"] = blog_totals["blog_name"].apply(
            lambda x: get_blog_group(all_blogs.get(x, ""))
        )
        blog_totals = blog_totals.sort_values("포스트 수", ascending=False)
        blog_totals = blog_totals[["그룹", "blog_name", "포스트 수"]].rename(columns={"blog_name": "블로그"})
        st.dataframe(blog_totals, use_container_width=True, hide_index=True)

# ============================================================
# Tab 2: 블로그별 개별 현황판
# ============================================================
with tab2:
    st.subheader("🏢 블로그별 개별 포스팅 현황판")
    st.caption("등록된 모든 업체 블로그별 개별 포스팅 수를 독립적으로 시각화합니다")

    if "blog_name" in df.columns:
        blog_names = df["blog_name"].unique().tolist()
        blog_counts = df.groupby("blog_name").size().to_dict()

        # 블로그별 개별 카드
        cols_per_row = 3
        rows = [blog_names[i:i+cols_per_row] for i in range(0, len(blog_names), cols_per_row)]

        for row_blogs in rows:
            cols = st.columns(cols_per_row)
            for idx, blog_name in enumerate(row_blogs):
                blog_id = all_blogs.get(blog_name, "")
                group = get_blog_group(blog_id)
                color = get_blog_color(blog_id)
                count = blog_counts.get(blog_name, 0)
                blog_df = df[df["blog_name"] == blog_name]

                with cols[idx]:
                    st.markdown(f"""
                    <div style="background: white; border-left: 4px solid {color};
                                padding: 15px; border-radius: 8px; margin-bottom: 10px;
                                box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                        <div style="font-size: 12px; color: #888;">{group}</div>
                        <div style="font-size: 16px; font-weight: bold; margin: 4px 0;">{blog_name}</div>
                        <div style="font-size: 28px; font-weight: bold; color: {color};">{count}건</div>
                    </div>
                    """, unsafe_allow_html=True)

                    # 미니 일별 차트
                    if not blog_df.empty and "date" in blog_df.columns:
                        mini_daily = blog_df.groupby(blog_df["date"].dt.date).size().reset_index(name="cnt")
                        mini_daily.columns = ["date", "cnt"]
                        fig = px.bar(mini_daily, x="date", y="cnt", height=120)
                        fig.update_layout(
                            margin=dict(l=0, r=0, t=0, b=0),
                            xaxis=dict(showticklabels=False, title=""),
                            yaxis=dict(showticklabels=False, title=""),
                            showlegend=False,
                        )
                        fig.update_traces(marker_color=color)
                        st.plotly_chart(fig, use_container_width=True, key=f"mini_{blog_name}")

        # ---- 전체 비교 바 차트 ----
        st.markdown("---")
        st.subheader("📊 전체 블로그 포스팅 수 비교")

        bar_df = df.groupby("blog_name").size().reset_index(name="count").sort_values("count", ascending=True)
        bar_df["color"] = bar_df["blog_name"].apply(lambda x: get_blog_color(all_blogs.get(x, "")))
        bar_df["group"] = bar_df["blog_name"].apply(lambda x: get_blog_group(all_blogs.get(x, "")))

        fig = px.bar(
            bar_df, x="count", y="blog_name", orientation="h",
            color="group", title=f"블로그별 포스팅 수 ({period})",
            color_discrete_map={
                "🔵 신촌지사": "#1565C0",
                "🟢 본사": "#2E7D32",
                "🔴 경쟁사": "#E53935",
            },
        )
        fig.update_layout(yaxis_title="", xaxis_title="포스트 수", height=max(400, len(bar_df) * 35))
        st.plotly_chart(fig, use_container_width=True)

        # ---- 최근 포스트 목록 ----
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

# ============================================================
# Tab 3: 주제별 분석
# ============================================================
with tab3:
    st.subheader("🏷️ 주제별 포스팅 분석")

    if "main_category" in df.columns:
        col_a, col_b = st.columns(2)
        cat_counts = df["main_category"].value_counts().reset_index()
        cat_counts.columns = ["category", "count"]

        with col_a:
            fig = px.pie(cat_counts, values="count", names="category",
                         title="주제 분포", hole=0.4)
            st.plotly_chart(fig, use_container_width=True)

        with col_b:
            fig = px.bar(cat_counts.sort_values("count", ascending=True),
                        x="count", y="category", orientation="h",
                        title="주제별 포스트 수", color="count",
                        color_continuous_scale="Blues")
            fig.update_layout(yaxis_title="", xaxis_title="포스트 수")
            st.plotly_chart(fig, use_container_width=True)

        # 히트맵
        st.subheader("🗺️ 블로그 x 주제 히트맵")
        cross = pd.crosstab(df["blog_name"], df["main_category"])
        fig = px.imshow(cross, text_auto=True, title="어떤 블로그가 어떤 주제를 다루는지",
                       color_continuous_scale="YlOrRd", aspect="auto")
        fig.update_layout(height=max(400, len(cross) * 30))
        st.plotly_chart(fig, use_container_width=True)

        # 놓치는 주제
        st.subheader("🚨 놓치고 있는 주제")
        own_ids_set = set(OWN_BLOGS.values())
        own_cats = df[df["blog_id"].isin(own_ids_set)]["main_category"].value_counts().to_dict()
        comp_cats = df[~df["blog_id"].isin(own_ids_set)]["main_category"].value_counts().to_dict()

        missed = []
        for cat in set(list(own_cats.keys()) + list(comp_cats.keys())):
            oc = own_cats.get(cat, 0)
            cc = comp_cats.get(cat, 0)
            if cc > 0 and oc == 0:
                missed.append({"주제": cat, "경쟁사": cc, "본사": oc, "상태": "🔴 미다룸"})
            elif cc > oc * 2 and cc > 2:
                missed.append({"주제": cat, "경쟁사": cc, "본사": oc, "상태": "🟡 부족"})

        if missed:
            st.error(f"⚠️ {len(missed)}개 주제에서 경쟁사 대비 뒤처지고 있습니다!")
            st.dataframe(pd.DataFrame(missed), use_container_width=True, hide_index=True)
        else:
            st.success("✅ 주요 트렌드를 놓치지 않고 있습니다!")

# ============================================================
# Tab 4: AI 리포트 + 내보내기
# ============================================================
with tab4:
    st.subheader("🤖 AI 리포트 및 자동 배포")
    st.caption("분석된 데이터를 실무에 바로 활용할 수 있도록 AI가 자동 분석합니다")

    # ---- AI 분석 실행 ----
    if st.button("🔮 AI 분석 실행 (전날/당일 포스팅 키워드 및 트렌드 요약)", use_container_width=True, type="primary"):
        from config.settings import ANTHROPIC_API_KEY
        if not ANTHROPIC_API_KEY:
            st.error("⚠️ ANTHROPIC_API_KEY가 설정되지 않았습니다.")
            st.info("""
**Streamlit Cloud 설정:**
1. 우측 하단 **Manage app** → **Settings** → **Secrets**
2. 아래 입력 후 Save:
```toml
ANTHROPIC_API_KEY = "sk-ant-여기에_키_입력"
```
            """)
        else:
            with st.spinner("Claude AI가 분석 중... (30초~1분)"):
                try:
                    import anthropic

                    own_ids_set = set(OWN_BLOGS.values())
                    own_df = df[df["blog_id"].isin(own_ids_set)]
                    comp_df = df[~df["blog_id"].isin(own_ids_set)]
                    own_cats = own_df["main_category"].value_counts().to_dict() if "main_category" in df.columns else {}
                    comp_cats = comp_df["main_category"].value_counts().to_dict() if "main_category" in df.columns else {}

                    missed_topics = {}
                    for cat in set(list(own_cats.keys()) + list(comp_cats.keys())):
                        oc = own_cats.get(cat, 0)
                        cc = comp_cats.get(cat, 0)
                        if (cc > 0 and oc == 0) or cc > oc * 2:
                            missed_topics[cat] = cc

                    titles_by_blog = {}
                    for _, row in df.sort_values("date", ascending=False).head(40).iterrows():
                        b = row.get("blog_name", "")
                        if b not in titles_by_blog:
                            titles_by_blog[b] = []
                        titles_by_blog[b].append(row.get("title", ""))

                    prompt = f"""당신은 영국 유학 시장 전문 분석가입니다.

## 분석 대상
- 영국유학센터 신촌지사 vs 본사 2개 vs 경쟁사 {len(COMPETITOR_BLOGS) + len(custom_comps)}개
- 기간: {period} ({len(df)}건 분석)

## 신촌지사 + 본사 포스팅 ({len(own_df)}건)
주제 분포: {json.dumps(own_cats, ensure_ascii=False)}

## 경쟁사 포스팅 ({len(comp_df)}건)
주제 분포: {json.dumps(comp_cats, ensure_ascii=False)}

## 본사가 놓치는 주제
{json.dumps(missed_topics, ensure_ascii=False)}

## 블로그별 최근 포스트 제목
{json.dumps(titles_by_blog, ensure_ascii=False, indent=1)}

다음을 분석해주세요:

### 1. 📊 오늘의 핵심 요약
- 가장 활발한 경쟁사와 그 주요 포스팅 주제
- 포스팅 키워드 트렌드

### 2. 🔥 주요 트렌드 (TOP 5)
- 현재 업계에서 가장 많이 다루는 주제

### 3. ⚠️ 놓치고 있는 기회
- 경쟁사가 다루지만 신촌지사/본사가 놓치고 있는 주제
- 구체적 대응 방안

### 4. 🏢 경쟁사별 동향
- 각 주요 경쟁사의 콘텐츠 전략 특징

### 5. ✍️ 즉시 작성 추천 콘텐츠 (5개)
- 구체적인 블로그 제목과 키워드 포함

### 6. 🔑 SEO 키워드 기회
- 선점할 수 있는 검색 키워드 5개

한국어로, 실행 가능한 구체적 인사이트를 제공하세요."""

                    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
                    response = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=3000,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    ai_result = response.content[0].text

                    # 저장
                    analysis_save = {
                        "period": period,
                        "generated_at": datetime.now().isoformat(),
                        "total_posts": len(df),
                        "ai_analysis": ai_result,
                        "posting_by_category": df["main_category"].value_counts().to_dict() if "main_category" in df.columns else {},
                        "top_keywords": [],
                        "own_vs_competitor": {
                            "own_total": len(own_df),
                            "competitor_total": len(comp_df),
                            "own_categories": own_cats,
                            "competitor_categories": comp_cats,
                            "missed_topics": missed_topics,
                        },
                    }
                    analysis_file = DATA_DIR / f"analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                    with open(analysis_file, "w", encoding="utf-8") as f:
                        json.dump(analysis_save, f, ensure_ascii=False, indent=2)

                    st.success("✅ AI 분석 완료!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"AI 분석 실패: {e}")

    st.markdown("---")

    # ---- AI 분석 결과 표시 ----
    analysis = load_latest_analysis()
    if analysis and analysis.get("ai_analysis"):
        st.markdown(analysis["ai_analysis"])
        st.caption(f"📅 분석 시각: {analysis.get('generated_at', '-')[:16]}")

        st.markdown("---")

        # ---- 내보내기 기능 ----
        st.subheader("📥 리포트 내보내기")
        st.caption("생성된 리포트를 클릭 한 번으로 다운로드 및 공유할 수 있습니다")

        col_dl1, col_dl2 = st.columns(2)

        # PDF 내보내기
        with col_dl1:
            try:
                from reports.pdf_generator import PDFReportGenerator
                if st.button("📄 PDF 리포트 다운로드", use_container_width=True):
                    with st.spinner("PDF 생성 중..."):
                        gen = PDFReportGenerator(analysis)
                        pdf_path = gen.generate()
                        with open(pdf_path, "rb") as f:
                            st.download_button(
                                "💾 PDF 파일 저장",
                                data=f.read(),
                                file_name=f"UK센터_블로그분석_{datetime.now().strftime('%Y%m%d')}.pdf",
                                mime="application/pdf",
                                use_container_width=True,
                            )
            except ImportError:
                st.info("PDF 생성은 로컬 서버에서 가능합니다 (reportlab 필요)")

        # Word(DOCX) 내보내기
        with col_dl2:
            ai_text = analysis.get("ai_analysis", "")
            report_date = datetime.now().strftime("%Y-%m-%d")

            # 마크다운 → 텍스트 변환하여 Word로 내보내기
            docx_content = f"""UK Centre 경쟁사 블로그 분석 리포트
생성일: {report_date}
분석 기간: {analysis.get('period', '-')}
총 포스트: {analysis.get('total_posts', 0)}건
{'='*60}

{ai_text}

{'='*60}
UK Centre Blog Analysis System - 자동 생성 리포트
"""
            st.download_button(
                "📝 Word(.txt) 리포트 다운로드",
                data=docx_content.encode("utf-8"),
                file_name=f"UK센터_블로그분석_{report_date}.txt",
                mime="text/plain",
                use_container_width=True,
            )

    else:
        st.info("아직 AI 분석 결과가 없습니다. 위의 '🔮 AI 분석 실행' 버튼을 클릭하세요.")

# ============================================================
# 사이드바 하단 정보
# ============================================================
st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 모니터링 현황")
st.sidebar.markdown(f"🔵 **신촌지사**: {len(SINCHON_BLOGS)}개")
st.sidebar.markdown(f"🟢 **본사**: {len(HQ_BLOGS)}개")
st.sidebar.markdown(f"🔴 **경쟁사(고정)**: {len(COMPETITOR_BLOGS)}개")
if custom_comps:
    st.sidebar.markdown(f"🟠 **경쟁사(추가)**: {len(custom_comps)}개")
st.sidebar.markdown(f"**총**: {len(all_blogs)}개 블로그")

st.sidebar.markdown("---")
st.sidebar.caption("UK Centre Blog Analysis v2.0")
st.sidebar.caption(f"데이터: {len(posts)}건 로드됨")
