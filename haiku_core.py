
from __future__ import annotations
import re
import pandas as pd
import streamlit as st

# =============================
# 日本的情緒 定義（13種）
# =============================
AESTHETICS = [
    "スキップ","侘び","寂び","幽玄","もののあはれ",
    "風雅","無常","愛らしさ","素朴","滑稽","淡白","静寂","余情"
]
AESTHETIC_INFO = {
    "スキップ": "今回は情緒指定を行わず、他の条件を優先します。",

    "侘び": "素朴・不完全の美。整いすぎない形や静かな孤独に美を見出す。"
            "→ 彩度を抑え、余白を広く取り、和紙の質感や滲みを生かす。"
            "“欠け”や“粗さ”がむしろ深みを与える。",

    "寂び": "古びの味わい・時間の痕跡。歳月が刻んだ静かな美。"
            "→ 錆色や風化した木、にじみのある筆致などを表現。"
            "朽ちゆくものの中に生命の余韻を感じる。",

    "幽玄": "見えない深み・余韻の美。すべてを語らず、想像に委ねる。"
            "→ 霞や遠景、藍の層で輪郭を曖昧にし、光と影で深さを示す。"
            "“見えないもの”が心を動かす世界。",

    "もののあはれ": "移ろいへの感受。儚く消えゆく瞬間に心を寄せる美意識。"
            "→ 落葉・夕暮・川音など、去りゆくものを描く。"
            "感情を抑えつつ、無常を受け入れる優しさを持つ。",

    "風雅": "気品・洗練。控えめで上品な趣。"
            "→ 構図は端正に、間（ま）を大切にし、金や光をさりげなく添える。"
            "優雅で凛とした印象を与える。",

    "無常": "うつり変わり・儚さ。永遠ではないものへの慈しみ。"
            "→ 消えゆく光や淡い明暗差、雲の流れなどを通して“今この瞬間”を描く。"
            "生と死の循環を静かに受け止める感性。",

    "愛らしさ": "小動物や子どもの可憐さ。小さな命へのまなざし。"
            "→ うさぎ・雀・子どもなどを主役にしすぎず、自然の中に溶け込ませる。"
            "生命のあたたかさをそっと伝える。",

    "素朴": "飾り気のなさ・自然体の美。"
            "→ 単純な形、控えめな色彩、過剰な装飾を避ける。"
            "無理のない姿の中に安らぎが宿る。",

    "滑稽": "ユーモア・可笑しみ。人や動物の“ちょっとしたズレ”に愛嬌を見出す。"
            "→ 表情や配置に軽いひねりを入れ、温かみのある笑いを生む。"
            "一茶らしい人間味を感じさせる美。",

    "淡白": "あっさり・簡素。余分を削ぎ落とし、静けさを残す美。"
            "→ 筆数を抑え、広い余白を取り、色彩を最小限に。"
            "潔く、澄みきった世界を描く。",

    "静寂": "静けさの美。音のない空間に心の声を聴く感性。"
            "→ 空・水面・雪など、動きを抑えたフラットな面を広く使う。"
            "無言の中に温度と気配を感じさせる。",

    "余情": "言外の余韻。語らぬ部分に情を残す美。"
            "→ 断片を置き、すべてを語らない構図にする。"
            "“続きを見る者の心に委ねる”という詩的な間（ま）の美学。"
}


SYNONYMS = {
    "子供": ["子供", "子", "童", "児", "小僧", "小坊主"],
    "海": ["海", "夏の海", "海士", "海苔", "海辺"],
    "桜": ["桜", "桜花", "遅桜", "山桜"],
}

@st.cache_data(show_spinner=False)
def load_haiku_df(path: str) -> pd.DataFrame:
    """CSV を読み込んで必要な列を補完."""
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception as e:
        st.error(f"CSV読込エラー: {e}")
        df = pd.DataFrame()

    for col in ["俳句","読み","季語候補","季節","plutchik_main","nihon_main","nihon_sub","出典","年"]:
        if col not in df.columns:
            df[col] = ""
    return df

def pick_references(df: pd.DataFrame, season: str, plutchik: str, aesthetic: str,
                    keyword: str, k: int = 3, prioritize_giongo: bool = True):
    """
    参照句を抽出。元アプリと同等のロジック。
    """
    search_terms = SYNONYMS.get(keyword, [keyword]) if keyword else []
    pattern = "|".join(map(re.escape, search_terms)) if search_terms else None

    df_base = df.copy()
    if season:
        df_base = df_base[df_base["季節"] == season]
    if plutchik:
        df_base = df_base[df_base["plutchik_main"] == plutchik]
    if aesthetic and aesthetic != "スキップ":
        df_base = df_base[df_base["nihon_main"] == aesthetic]

    if pattern:
        df_free = df[
            df["俳句"].astype(str).str.contains(pattern, na=False) |
            df["読み"].astype(str).str.contains(pattern, na=False) |
            df["季語候補"].astype(str).str.contains(pattern, na=False)
        ]
    else:
        df_free = df.iloc[0:0]

    results = []
    if prioritize_giongo:
        df_giongo = df[df.get("has_repetition") == True]
        if not df_giongo.empty:
            results.append(df_giongo.sample(1).iloc[0])

    if not df_free.empty:
        results.append(df_free.sample(1).iloc[0])

    for _, r in df_base.head(10).iterrows():
        if len(results) >= k:
            break
        if not any(str(res["俳句"]) == str(r["俳句"]) for res in results):
            results.append(r)

    if len(results) < k and not df_free.empty:
        for _, r in df_free.iterrows():
            if len(results) >= k:
                break
            if not any(str(res["俳句"]) == str(r["俳句"]) for res in results):
                results.append(r)

    refs = []
    for r in results[:k]:
        src = f"{str(r.get('出典','')).strip()} ({str(r.get('年','')).strip()})"
        refs.append({
            "text":       str(r["俳句"]),
            "source":     src,
            "season":     str(r.get("季節","")),
            "plutchik":   str(r.get("plutchik_main","")),
            "aesthetic":  str(r.get("nihon_main","")),
            "has_repetition": bool(r.get("has_repetition", False))
        })
    return refs
