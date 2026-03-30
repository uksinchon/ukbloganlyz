"""
PDF 리포트 생성기
- 분석 결과를 상세 PDF 리포트로 변환
- 차트, 표, AI 분석 인사이트 포함
"""
import logging
from datetime import datetime
from pathlib import Path
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, HRFlowable,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

from config.settings import REPORT_DIR

logger = logging.getLogger(__name__)

# 한글 폰트 설정 시도
KOREAN_FONT_REGISTERED = False
try:
    # 시스템에서 한글 폰트 찾기
    font_paths = [
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/nanum/NanumGothic.ttf",
        "/System/Library/Fonts/AppleGothic.ttf",
        "C:/Windows/Fonts/malgun.ttf",
    ]
    for fp in font_paths:
        if Path(fp).exists():
            pdfmetrics.registerFont(TTFont("Korean", fp))
            KOREAN_FONT_REGISTERED = True
            # matplotlib 한글 설정
            plt.rcParams["font.family"] = fm.FontProperties(fname=fp).get_name()
            break
except Exception:
    pass

if not KOREAN_FONT_REGISTERED:
    logger.warning("한글 폰트를 찾을 수 없습니다. 기본 폰트를 사용합니다.")
    plt.rcParams["font.family"] = "DejaVu Sans"


class PDFReportGenerator:
    """PDF 리포트 생성"""

    def __init__(self, analysis_data: dict):
        self.data = analysis_data
        self.styles = getSampleStyleSheet()
        self._setup_styles()

    def _setup_styles(self):
        font_name = "Korean" if KOREAN_FONT_REGISTERED else "Helvetica"

        self.styles.add(ParagraphStyle(
            name="KoreanTitle",
            fontName=font_name,
            fontSize=24,
            spaceAfter=20,
            textColor=colors.HexColor("#1a237e"),
            leading=30,
        ))
        self.styles.add(ParagraphStyle(
            name="KoreanH2",
            fontName=font_name,
            fontSize=16,
            spaceBefore=15,
            spaceAfter=10,
            textColor=colors.HexColor("#283593"),
            leading=22,
        ))
        self.styles.add(ParagraphStyle(
            name="KoreanH3",
            fontName=font_name,
            fontSize=13,
            spaceBefore=10,
            spaceAfter=6,
            textColor=colors.HexColor("#3949ab"),
            leading=18,
        ))
        self.styles.add(ParagraphStyle(
            name="KoreanBody",
            fontName=font_name,
            fontSize=10,
            spaceAfter=6,
            leading=16,
        ))
        self.styles.add(ParagraphStyle(
            name="KoreanSmall",
            fontName=font_name,
            fontSize=8,
            textColor=colors.grey,
            leading=12,
        ))

    # ----------------------------------------------------------
    # 차트 생성
    # ----------------------------------------------------------
    def _create_bar_chart(self, data: dict, title: str, xlabel: str = "", ylabel: str = "포스트 수") -> BytesIO:
        fig, ax = plt.subplots(figsize=(8, 4))
        labels = list(data.keys())[:15]
        values = [data[k] for k in labels]

        bar_colors = plt.cm.Blues([(v / max(values) * 0.6 + 0.3) if max(values) > 0 else 0.5 for v in values])
        bars = ax.barh(labels, values, color=bar_colors)
        ax.set_xlabel(ylabel)
        ax.set_title(title, fontsize=14, fontweight="bold")
        ax.invert_yaxis()

        for bar, val in zip(bars, values):
            ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                    str(val), va="center", fontsize=9)

        plt.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf

    def _create_pie_chart(self, data: dict, title: str) -> BytesIO:
        fig, ax = plt.subplots(figsize=(6, 6))
        labels = list(data.keys())[:10]
        values = [data[k] for k in labels]

        wedges, texts, autotexts = ax.pie(
            values, labels=labels, autopct="%1.1f%%",
            colors=plt.cm.Set3.colors[:len(labels)],
            startangle=90,
        )
        ax.set_title(title, fontsize=14, fontweight="bold")

        plt.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf

    def _create_comparison_chart(self, own: dict, comp: dict) -> BytesIO:
        fig, ax = plt.subplots(figsize=(10, 5))

        all_cats = sorted(set(list(own.keys()) + list(comp.keys())))[:12]
        own_vals = [own.get(c, 0) for c in all_cats]
        comp_vals = [comp.get(c, 0) for c in all_cats]

        x = range(len(all_cats))
        width = 0.35
        ax.bar([i - width / 2 for i in x], own_vals, width, label="UK Centre (본사)", color="#1976D2")
        ax.bar([i + width / 2 for i in x], comp_vals, width, label="경쟁사", color="#FF7043")

        ax.set_xticks(list(x))
        ax.set_xticklabels(all_cats, rotation=45, ha="right", fontsize=8)
        ax.legend()
        ax.set_title("본사 vs 경쟁사 주제별 포스팅 비교", fontsize=14, fontweight="bold")
        ax.set_ylabel("포스트 수")

        plt.tight_layout()
        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf

    # ----------------------------------------------------------
    # PDF 빌드
    # ----------------------------------------------------------
    def generate(self) -> Path:
        """PDF 리포트 생성"""
        period = self.data.get("period", "분석")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = REPORT_DIR / f"blog_analysis_{timestamp}.pdf"
        REPORT_DIR.mkdir(parents=True, exist_ok=True)

        doc = SimpleDocTemplate(
            str(filename),
            pagesize=A4,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            leftMargin=2 * cm,
            rightMargin=2 * cm,
        )

        elements = []

        # ---- 표지 ----
        elements.append(Spacer(1, 3 * cm))
        elements.append(Paragraph(
            "UK Centre Blog Analysis Report",
            self.styles["KoreanTitle"],
        ))
        elements.append(Spacer(1, 1 * cm))
        elements.append(Paragraph(
            f"경쟁사 블로그 분석 리포트 - {period}",
            self.styles["KoreanH2"],
        ))
        elements.append(Spacer(1, 5 * mm))
        elements.append(Paragraph(
            f"생성일: {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')}",
            self.styles["KoreanBody"],
        ))
        elements.append(Paragraph(
            f"분석 대상 포스트: {self.data.get('total_posts', 0)}건",
            self.styles["KoreanBody"],
        ))
        elements.append(PageBreak())

        # ---- 목차 ----
        elements.append(Paragraph("목차", self.styles["KoreanH2"]))
        toc_items = [
            "1. 전체 포스팅 현황",
            "2. 블로그별 포스팅 수",
            "3. 주제별 분석",
            "4. 본사 vs 경쟁사 비교",
            "5. 놓치는 트렌드 분석",
            "6. 키워드 분석",
            "7. 경쟁사별 상세 분석",
            "8. AI 심층 분석 인사이트",
        ]
        for item in toc_items:
            elements.append(Paragraph(item, self.styles["KoreanBody"]))
        elements.append(PageBreak())

        # ---- 1. 전체 포스팅 현황 ----
        elements.append(Paragraph("1. 전체 포스팅 현황", self.styles["KoreanH2"]))
        elements.append(HRFlowable(width="100%", color=colors.HexColor("#1a237e")))
        elements.append(Spacer(1, 5 * mm))

        summary_data = [
            ["구분", "수치"],
            ["전체 분석 포스트", f"{self.data.get('total_posts', 0)}건"],
            ["본사 포스트", f"{self.data.get('own_vs_competitor', {}).get('own_total', 0)}건"],
            ["경쟁사 포스트", f"{self.data.get('own_vs_competitor', {}).get('competitor_total', 0)}건"],
            ["분석 블로그 수", f"{len(self.data.get('posting_by_blog', {}))}개"],
        ]
        table = Table(summary_data, colWidths=[200, 200])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a237e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (1, 0), (1, -1), "CENTER"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#E3F2FD")]),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 1 * cm))

        # ---- 2. 블로그별 포스팅 수 ----
        elements.append(Paragraph("2. 블로그별 포스팅 수", self.styles["KoreanH2"]))
        elements.append(HRFlowable(width="100%", color=colors.HexColor("#1a237e")))

        posting_by_blog = self.data.get("posting_by_blog", {})
        if posting_by_blog:
            chart = self._create_bar_chart(posting_by_blog, "Blog Posting Count by Source")
            elements.append(Image(chart, width=16 * cm, height=8 * cm))

        elements.append(PageBreak())

        # ---- 3. 주제별 분석 ----
        elements.append(Paragraph("3. 주제별 포스팅 분석", self.styles["KoreanH2"]))
        elements.append(HRFlowable(width="100%", color=colors.HexColor("#1a237e")))

        posting_by_cat = self.data.get("posting_by_category", {})
        if posting_by_cat:
            chart = self._create_pie_chart(posting_by_cat, "Topic Distribution")
            elements.append(Image(chart, width=12 * cm, height=12 * cm))

            # 테이블로도 표시
            cat_table_data = [["주제", "포스트 수", "비율"]]
            total = sum(posting_by_cat.values()) or 1
            for cat, count in posting_by_cat.items():
                pct = f"{count / total * 100:.1f}%"
                cat_table_data.append([cat, str(count), pct])

            table = Table(cat_table_data, colWidths=[150, 80, 80])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#283593")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#E8EAF6")]),
            ]))
            elements.append(Spacer(1, 5 * mm))
            elements.append(table)

        elements.append(PageBreak())

        # ---- 4. 본사 vs 경쟁사 비교 ----
        elements.append(Paragraph("4. 본사 vs 경쟁사 주제 비교", self.styles["KoreanH2"]))
        elements.append(HRFlowable(width="100%", color=colors.HexColor("#1a237e")))

        comparison = self.data.get("own_vs_competitor", {})
        if comparison:
            chart = self._create_comparison_chart(
                comparison.get("own_categories", {}),
                comparison.get("competitor_categories", {}),
            )
            elements.append(Image(chart, width=16 * cm, height=8 * cm))

        elements.append(PageBreak())

        # ---- 5. 놓치는 트렌드 ----
        elements.append(Paragraph("5. 놓치는 트렌드 분석 (경고)", self.styles["KoreanH2"]))
        elements.append(HRFlowable(width="100%", color=colors.HexColor("#d32f2f")))
        elements.append(Spacer(1, 5 * mm))

        missed = comparison.get("missed_topics", {})
        if missed:
            elements.append(Paragraph(
                "아래 주제들은 경쟁사가 활발히 다루고 있지만 본사(UK Centre)가 놓치고 있는 분야입니다.",
                self.styles["KoreanBody"],
            ))
            missed_data = [["놓치는 주제", "경쟁사 포스트 수", "긴급도"]]
            for topic, count in missed.items():
                urgency = "높음" if count >= 5 else "보통" if count >= 2 else "낮음"
                missed_data.append([topic, str(count), urgency])

            table = Table(missed_data, colWidths=[150, 100, 80])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d32f2f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ]))
            elements.append(table)
        else:
            elements.append(Paragraph(
                "현재 놓치는 주요 트렌드가 없습니다. 잘 하고 계십니다!",
                self.styles["KoreanBody"],
            ))

        elements.append(PageBreak())

        # ---- 6. 키워드 분석 ----
        elements.append(Paragraph("6. 상위 키워드 분석", self.styles["KoreanH2"]))
        elements.append(HRFlowable(width="100%", color=colors.HexColor("#1a237e")))

        keywords = self.data.get("top_keywords", [])
        if keywords:
            kw_dict = {k: v for k, v in keywords[:20]}
            chart = self._create_bar_chart(kw_dict, "Top Keywords")
            elements.append(Image(chart, width=16 * cm, height=8 * cm))

        elements.append(PageBreak())

        # ---- 7. 경쟁사별 상세 분석 ----
        elements.append(Paragraph("7. 경쟁사별 상세 분석", self.styles["KoreanH2"]))
        elements.append(HRFlowable(width="100%", color=colors.HexColor("#1a237e")))

        for detail in self.data.get("competitor_details", []):
            label = "본사" if detail.get("is_own") else "경쟁사"
            elements.append(Paragraph(
                f"[{label}] {detail['blog_name']} (총 {detail['total_posts']}건)",
                self.styles["KoreanH3"],
            ))

            if detail.get("top_categories"):
                cat_text = ", ".join(
                    f"{k}({v}건)" for k, v in detail["top_categories"].items()
                )
                elements.append(Paragraph(f"주요 주제: {cat_text}", self.styles["KoreanBody"]))

            if detail.get("recent_titles"):
                elements.append(Paragraph("최근 포스트:", self.styles["KoreanBody"]))
                for title in detail["recent_titles"][:3]:
                    elements.append(Paragraph(f"  - {title}", self.styles["KoreanSmall"]))

            elements.append(Spacer(1, 5 * mm))

        elements.append(PageBreak())

        # ---- 8. AI 분석 인사이트 ----
        elements.append(Paragraph("8. AI 심층 분석 인사이트", self.styles["KoreanH2"]))
        elements.append(HRFlowable(width="100%", color=colors.HexColor("#1a237e")))
        elements.append(Spacer(1, 5 * mm))

        ai_analysis = self.data.get("ai_analysis", "")
        if ai_analysis:
            # 줄바꿈 처리
            for line in ai_analysis.split("\n"):
                line = line.strip()
                if line.startswith("##"):
                    elements.append(Paragraph(line.replace("#", "").strip(), self.styles["KoreanH3"]))
                elif line.startswith("**") and line.endswith("**"):
                    elements.append(Paragraph(line.replace("**", ""), self.styles["KoreanH3"]))
                elif line:
                    elements.append(Paragraph(line, self.styles["KoreanBody"]))
        else:
            elements.append(Paragraph(
                "AI 분석을 사용하려면 ANTHROPIC_API_KEY를 설정해주세요.",
                self.styles["KoreanBody"],
            ))

        # ---- 푸터 ----
        elements.append(Spacer(1, 2 * cm))
        elements.append(HRFlowable(width="100%", color=colors.grey))
        elements.append(Paragraph(
            f"UK Centre Blog Analysis System | 자동 생성 리포트 | {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            self.styles["KoreanSmall"],
        ))

        # 빌드
        doc.build(elements)
        logger.info(f"PDF 리포트 생성: {filename}")
        return filename
