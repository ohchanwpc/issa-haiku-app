
import os
from pathlib import Path
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from PIL import Image

# ---- Local modules (5-file structure) ----
from haiku_core import load_haiku_df, pick_references
from haiku_gpt import call_gpt_haiku, generate_english_tweet_block
from image_gen import build_image_prompt, generate_image, save_artifacts
from x_client import post_to_x

# =============================
# App Config & ENV
# =============================
st.set_page_config(page_title="Haiku × Ukiyo-e Generator", page_icon="🍃", layout="centered")
load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    st.error("OPENAI_API_KEY が設定されていません。.env を確認してください。")
    st.stop()

ISSA_CSV_PATH = "haiku_with_repetition.csv"   # 必要に応じて変更
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# =============================
# UI CSS
# =============================
st.markdown("""
<style>
.block-container { max-width: 800px; margin: auto; }
div[data-testid="stImage"] { text-align: center; display: flex; justify-content: center; }
div[data-testid="stImage"] img, .stImage img, figure img { display: block; margin-left: auto; margin-right: auto; }
</style>
""", unsafe_allow_html=True)

st.title("🍃 俳句 × 浮世絵 生成")

st.markdown("""
<div style='font-size:14px; color:#555; margin-top:-10px;'>
小林一茶のまなざしを現代に。<br>
季節・感情・美意識を選び、AIとともに新しい俳句と浮世絵を生み出します。<br>
 
</div>
""", unsafe_allow_html=True)


# =============================
# Session State
# =============================
if "haiku_data" not in st.session_state: st.session_state.haiku_data = None
if "image_prompt" not in st.session_state: st.session_state.image_prompt = None
if "img" not in st.session_state: st.session_state.img = None
if "references" not in st.session_state: st.session_state.references = None
if "references_locked" not in st.session_state: st.session_state.references_locked = False
if "twitter_block" not in st.session_state: st.session_state.twitter_block = ""
if "op_name" not in st.session_state: st.session_state.op_name = ""
if "op_desc" not in st.session_state: st.session_state.op_desc = ""
if "op_traits" not in st.session_state:
    st.session_state.op_traits = [{"Trait Type": "Season", "Value": ""},
                                  {"Trait Type": "Emotion", "Value": ""}]

# =============================
# Controls
# =============================
from haiku_core import AESTHETICS, AESTHETIC_INFO
# ===== ステップ1の前に1行分の余白を入れる =====
st.write("")
# ===== ステップ1: 季節を選択 =====
if "season" not in st.session_state:
    st.session_state.season = "秋"

st.session_state.season = st.radio(
    "ステップ1: 季節を選択してください",
    ["春", "夏", "秋", "冬", "新年", "無季"],
    index=["春", "夏", "秋", "冬", "新年", "無季"].index(st.session_state.season),
    horizontal=True
)

# ===== ステップ2: 表現したい感情を選択 =====
if "plutchik" not in st.session_state:
    st.session_state.plutchik = "悲しみ"

st.session_state.plutchik = st.radio(
    "ステップ2: 表現したい感情を選択してください",
    ["喜び", "信頼", "恐れ", "驚き", "悲しみ", "嫌悪", "怒り", "期待"],
    index=["喜び", "信頼", "恐れ", "驚き", "悲しみ", "嫌悪", "怒り", "期待"].index(st.session_state.plutchik),
    horizontal=True
)

# ===== ステップ3: 日本的情緒を選択（フォームの外で即時更新） =====
if "aesthetic" not in st.session_state:
    st.session_state.aesthetic = "もののあはれ"

st.session_state.aesthetic = st.selectbox(
    "ステップ3: 俳句に含めたい日本的情緒を選択してください",
    options=AESTHETICS,
    index=AESTHETICS.index(st.session_state.aesthetic)
    if st.session_state.aesthetic in AESTHETICS else 0
)

selected_aesthetic = st.session_state.aesthetic
selected_info = AESTHETIC_INFO.get(selected_aesthetic, "情報がありません。")

# 1行プレビュー
st.markdown(f"🪶 **{selected_aesthetic}**：{selected_info.split('→')[0]}")

# 感情の核
emotion_core = {
    "侘び": "静けさの中の充足",
    "寂び": "時間の重みと味わい",
    "幽玄": "見えない深みの美",
    "もののあはれ": "移ろいへの共感",
    "風雅": "品位と間の美学",
    "無常": "儚さと受容のやさしさ",
    "愛らしさ": "小さな命へのまなざし",
    "素朴": "自然体で飾らない安らぎ",
    "滑稽": "人間味ある可笑しさ",
    "淡白": "潔さと澄んだ余白",
    "静寂": "音のない世界の響き",
    "余情": "語らぬ部分に宿る想い"
}


# ===== ステップ4以降: 参照句確定エリア =====
st.markdown("""
    <style>
    /* ステップ見出し */
    .step-label {
        font-size: 14px !important;      /* ステップ1と同じサイズ */
        font-weight: 400 !important;     /* 標準の太さ */
        margin-top: 0.8em !important;
        margin-bottom: -3.2em !important; /* ←ここを微調整 */
    }

    /* Streamlit の入力フォーム全般に適用 */
    div[data-baseweb="input"] {
        margin-top: 0 !important;        /* 上方向のマージンを削除 */
        padding-top: 0 !important;       /* 内側の余白も削除 */
    }
    textarea {
        margin-top: 0 !important;
        padding-top: 0 !important;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<p class="step-label">ステップ4: キーワード（例：川、家族、影）を入力してください</p>', unsafe_allow_html=True)
keyword = st.text_input("", value="紅葉")

st.markdown('<p class="step-label">ステップ5: あなたの体験メモを入力してください</p>', unsafe_allow_html=True)
experience = st.text_area("", value="風に散る紅葉の一枚が、掌に落ちてきた。命を燃やしきったあとの静けさが、そこにあった。人の一生もまた、かくのごとし。赤く散る葉を見送りながら、過ぎゆく日々を慈しむ心が生まれる。散ることは終わりではなく、土に還る約束なのだ。")

# ===== ステップ6: 擬音語優先チェック =====
prioritize_giongo = st.checkbox(
    "ステップ6: 擬音語（繰り返し表現）を優先する場合はチェックを入れてください",
    value=True
)



if st.button("ステップ7: 条件を確定（参照句を確定）"):
    df = load_haiku_df(ISSA_CSV_PATH)
    st.session_state.references = pick_references(
        df,
        season=st.session_state.season,
        plutchik=st.session_state.plutchik,
        aesthetic=st.session_state.aesthetic,
        keyword=keyword,
        k=3,
        prioritize_giongo=prioritize_giongo
    )
    st.session_state.references_locked = True
    st.session_state.haiku_data = None
    st.session_state.image_prompt = None
    st.session_state.img = None


# 参照句プレビュー
with st.expander("📚 参照句（小林一茶の俳句から選定条件を元に抽出された参照句です。）", expanded=False):
    if st.session_state.references_locked and st.session_state.references:
        import pandas as pd
        ref_df = pd.DataFrame(st.session_state.references).rename(columns={
            "text": "俳句", "source": "出典/年", "season": "季節", "plutchik": "感情", "aesthetic": "情緒"
        })
        ref_df.insert(0, "No.", [f"({i})" for i in range(1, len(ref_df)+1)])
        ref_df["俳句"] = ref_df.apply(lambda row: ("🎵 " if row.get("has_repetition") else "") + str(row["俳句"]), axis=1)
        st.dataframe(ref_df[["No.","俳句","季節","感情","情緒","出典/年"]], use_container_width=True, hide_index=True)
    else:
        st.info("まだ参照句が確定していません。上の『条件を確定（参照句を確定）』を押してください。")
    if st.button("参照句を再抽出（ロック解除）"):
        st.session_state.references_locked = False
        st.session_state.references = None
        st.session_state.haiku_data = None
        st.session_state.image_prompt = None
        st.session_state.img = None
        st.rerun()
DEBUG = False  # ← 本番時はFalse、開発時だけTrueに

if DEBUG:
    st.caption(
        f"🛠 state: refs_locked={st.session_state.get('references_locked')} / "
        f"haiku={'ok' if st.session_state.get('haiku_data') else '-'} / "
        f"prompt={'ok' if st.session_state.get('image_prompt') else '-'} / "
        f"img={'ok' if st.session_state.get('img') is not None else '-'}"
    )

col1, col2 = st.columns(2)

# ① 俳句生成
with col1:
    if st.button("① 俳句生成", key="btn_make_haiku"):
        if not (st.session_state.references_locked and st.session_state.references):
            st.warning("参照句が未確定です。『条件を確定（参照句を確定）』を押してください。")
        else:
            payload = {
                "season": st.session_state.season,
                "plutchik": st.session_state.plutchik,
                "aesthetic": st.session_state.aesthetic,
                "keyword": keyword,
                "experience": experience,
                "references": st.session_state.references
            }
            with st.spinner("俳句を生成中..."):
                st.session_state.haiku_data = call_gpt_haiku(payload)

            if st.session_state.haiku_data:
                h = st.session_state.haiku_data
                st.session_state.image_prompt = build_image_prompt(
                    haiku_ja=h.get("haiku_ja", ""),
                    explanation_ja=h.get("explanation_ja", ""),
                    season=st.session_state.season,
                    keyword=keyword,
                    aesthetic=st.session_state.aesthetic
                )

with col2:
    st.caption("①で俳句を確定 → 下の②画像生成ボタンで画像生成できます。")

# 俳句表示
if st.session_state.get("haiku_data"):
    h = st.session_state.haiku_data
    haiku_ja = h.get("haiku_ja","")
    explanation_ja = h.get("explanation_ja") or h.get("explanation") or ""
    reasons_refs_ja = (h.get("reasons_refs_ja","") or "").replace("\\n", "\n")

    st.subheader("🌿 新作俳句（日本語）")
    st.markdown(
        f"<p style='font-size:28px; font-weight:bold; text-align:center;'>{haiku_ja}</p>",
        unsafe_allow_html=True
    )

    with st.expander("📖 意訳・背景（俳句の情景と感情）", expanded=True):
        st.markdown(explanation_ja if explanation_ja.strip() else "（意訳なし）")

    with st.expander("🧭 参照句の要素をどう使ったか", expanded=True):
        st.markdown(reasons_refs_ja or "（理由なし）")

from PIL import Image
from datetime import datetime
from pathlib import Path

# ── ②画像生成セクション（“参照句をどう使ったか”の直下に配置してください） ──
if st.session_state.get("haiku_data"):

    with st.container():  # ← この中で順序を固定
        # 1) ②ボタン（常に一番上に出る）
        clicked = st.button("② 画像生成（1024x1024）", key="btn_make_image")

        # 2) ここで “画像を表示する置き場” をボタンの下に確保
        image_area = st.container()

        # 3) 押されたら生成
        if clicked:
            if not st.session_state.get("image_prompt"):
                st.warning("先に『① 俳句生成』を実行してください。")
            else:
                with st.spinner("浮世絵風画像を生成中..."):
                    img = generate_image(st.session_state.image_prompt, size="1024x1024")
                if isinstance(img, Image.Image):
                    img = img.convert("RGB").copy()
                st.session_state.img = img

                # 保存（DLボタン用のパスも保持）
                meta = {
                    "season": st.session_state.season,
                    "plutchik": st.session_state.plutchik,
                    "aesthetic": st.session_state.aesthetic,
                    "keyword": keyword,
                    "experience": experience,
                    "haiku": {"ja": st.session_state.haiku_data.get("haiku_ja","")},
                    "explanation_ja": st.session_state.haiku_data.get("explanation_ja",""),
                    "reasons_ja": st.session_state.haiku_data.get("reasons_ja",""),
                    "references": st.session_state.haiku_data.get("references", []),
                    "image_prompt": st.session_state.image_prompt,
                    "size": "1024x1024",
                    "model": "gpt-image-1",
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                }
                st.session_state.img_paths = save_artifacts(st.session_state.img, meta, output_dir=OUTPUT_DIR)
            

        # 4) 画像とDLボタンは “必ずボタンの下” に描画
        with image_area:
            if st.session_state.get("img") is not None:
                st.subheader("🖼️ 生成画像")
                st.image(st.session_state.img, caption="1024x1024 / Utagawa Hiroshige style", width=500)

                paths = st.session_state.get("img_paths")
                if paths:
                    with open(paths["png"], "rb") as f:
                        st.download_button(
                            "📥 画像PNGをダウンロード",
                            data=f,
                            file_name=Path(paths["png"]).name,
                            mime="image/png",
                            key=f"download_png_{Path(paths['png']).name}"  # 重複防止
                        )



# ③ 英語俳句（X用）生成
st.markdown("---")
if st.button("③ 英語俳句を生成", key="btn_make_english"):
    if not st.session_state.get("haiku_data"):
        st.warning("先に『① 俳句生成』を実行してください。")
    else:
        h = st.session_state.haiku_data
        with st.spinner("英語俳句を生成中..."):
            st.session_state.twitter_block = generate_english_tweet_block(
                h.get("haiku_ja",""), h.get("explanation_ja","")
            )

if st.session_state.get("twitter_block"):
    st.text_area("English post", value=st.session_state.twitter_block, height=220)


# ==== ④ 画像を英語俳句入りで再出力（API合成：画像内に文字） ==========================
from image_gen import edit_image_with_text
import re, io
import streamlit as st

st.markdown("### ④ 画像を英語俳句入りで再出力")

base_img = st.session_state.get("img")
twitter_block = st.session_state.get("twitter_block") or ""

def extract_haiku_en_from_block(block: str) -> str:
    cleaned = block.replace("```", "").strip()
    m = re.search(r"🍃\s*Haiku\s*\(English\)\s*\n+(.+?)\n+\s*✨\s*Explanation",
                  cleaned, flags=re.DOTALL | re.IGNORECASE)
    if not m: return ""
    lines = [ln.rstrip() for ln in m.group(1).strip().splitlines()]
    compact = []
    for ln in lines:
        if ln.strip()=="":
            if compact and compact[-1]!="": compact.append("")
        else:
            compact.append(ln)
    return "\n".join(compact).strip()

haiku_en = extract_haiku_en_from_block(twitter_block).strip() or \
           ((st.session_state.get("haiku_en") or "") or
            ((st.session_state.get("haiku_data") or {}).get("haiku_en","") or "")).strip()

# --- 初期化（session_state を唯一の真実に） ---
POS_ANCHOR_TEXT = {
    "下部中央": "bottom-center",
    "右下":     "bottom-right",
    "左下":     "bottom-left",
    "中央":     "center",
    "右上":     "top-right",
    "左上":     "top-left",
    "上部中央": "top-center"
}
if "pos_choice" not in st.session_state:
    st.session_state.pos_choice = "左上"
if "inset_pct" not in st.session_state:
    st.session_state.inset_pct = 5
if "min_bottom_px" not in st.session_state:
    st.session_state.min_bottom_px = 52
if "line_spacing" not in st.session_state:
    st.session_state.line_spacing = 1.35
if "auto_sync_layout" not in st.session_state:
    st.session_state.auto_sync_layout = True

def build_directives(haiku_en, anchor_text, inset_pct, min_bottom_px, line_spacing):
    return f"""Typeset the following English haiku **inside the existing artwork** (no bands, no extra margins, no canvas expansion).
Use Allura font; if unavailable, use a similar elegant script. Keep exact line breaks; no quotes, no extra text:
{haiku_en}

Layout constraints (important):
- Do not add any translucent band, shape, or new margins.
- Place the poem at the {anchor_text} area of the scene.
- Respect a safe inset of {inset_pct}% from all edges; no glyph may touch or cross the edges.
- Keep the text baseline at least {min_bottom_px}px above the bottom edge (on a 1024×1024 canvas).
- If there is any risk of clipping, automatically reduce the font size and increase line spacing to about {line_spacing}×.
- Apply a subtle shadow or thin outline for legibility, but keep it unobtrusive.
- Preserve the ukiyo-e look-and-feel; do not alter the scene except placing the text.
- Final output must be exactly 1024×1024."""

# 初期のレイアウト指示
if "remix_directives_area" not in st.session_state:
    st.session_state.remix_directives_area = build_directives(
        haiku_en,
        POS_ANCHOR_TEXT[st.session_state.pos_choice],
        st.session_state.inset_pct,
        st.session_state.min_bottom_px,
        st.session_state.line_spacing,
    )

if base_img is None:
    st.info("まず②で画像を生成してください。")
elif not haiku_en:
    st.info("まず③で英語俳句を生成してください。")
else:
    # === 位置の選択 ===
    options = ["下部中央", "右下", "左下", "中央", "右上", "左上", "上部中央"]

    # 初期化：最初の一回だけ既定値を入れる
    if "pos_choice" not in st.session_state:
        st.session_state.pos_choice = "左上"  # 既定値

    # 初回は index を渡し、それ以降は渡さない（警告防止）
    if "pos_choice__inited" not in st.session_state:
        choice = st.radio(
            "文字の配置（画像内）",
            options,
            index=options.index(st.session_state.pos_choice),
            key="pos_choice",
            horizontal=True
        )
        st.session_state.pos_choice__inited = True
    else:
        choice = st.radio(
            "文字の配置（画像内）",
            options,
            key="pos_choice",
            horizontal=True
        )



    # 自動同期トグル
    st.checkbox("配置変更に合わせてレイアウト指示を自動更新する",
                key="auto_sync_layout")

    # ===== 折り畳み：詳細調整 =====
    with st.expander("🎛 レイアウト調整（必要な時だけ開く）", expanded=False):
        st.session_state.inset_pct = st.slider("端からのインセット（%）", 2, 10, st.session_state.inset_pct, 1)
        st.session_state.min_bottom_px = st.slider("下端からの最低ベースライン距離（px）", 24, 96, st.session_state.min_bottom_px, 4)
        st.session_state.line_spacing = st.slider("行間倍率", 1.1, 1.8, st.session_state.line_spacing, 0.05)

    # 自動同期がONなら、毎リランで指示を最新化
    if st.session_state.auto_sync_layout:
        st.session_state.remix_directives_area = build_directives(
            haiku_en,
            POS_ANCHOR_TEXT[st.session_state.pos_choice],
            st.session_state.inset_pct,
            st.session_state.min_bottom_px,
            st.session_state.line_spacing,
        )

    # ユーザー編集可（Single Source of Truth は session_state）
    # 変更後（折り畳み式に）：
    with st.expander("📝 レイアウト指示文（必要な時だけ編集）", expanded=False):
        directives = st.text_area(
            "（必要に応じて編集してください）",
            value=st.session_state.remix_directives_area,
            key="remix_directives_area",
            height=260
        )
    # 実行ボタン
    if st.button("④ 英語俳句入りで再出力", key="btn_remix_en_overlay"):
        with st.spinner("英語俳句を画像に配置中..."):
            final_img = edit_image_with_text(base_img, directives, size="1024x1024")

        if final_img.size != base_img.size:
            final_img = final_img.resize(base_img.size)

        st.session_state.img_with_en = final_img
        st.image(final_img, caption="✅ 最終画像（画像内に英語俳句）", width=500)

        buf = io.BytesIO()
        final_img.save(buf, format="PNG")
        st.download_button(
            "📥 最終画像PNGをダウンロード",
            data=buf.getvalue(),
            file_name="artwork_final_with_english_haiku.png",
            mime="image/png"
        )
