import os
from pathlib import Path
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv
from PIL import Image
import traceback  # ← 追加（例外の全文を表示するため）

# ---- Local modules (5-file structure) ----
try:
    from haiku_core import load_haiku_df, pick_references
    from haiku_gpt import call_gpt_haiku, generate_english_tweet_block
    from image_gen import build_image_prompt, generate_image, save_artifacts
    from x_client import post_to_x
except Exception as e:
    # Streamlit UI に赤枠で表示
    st.error("❌ モジュールの読み込みに失敗しました。詳細を以下に表示します。")
    # 例外トレース全文をUIに出力
    st.code(traceback.format_exc(), language="python")
    # この時点でアプリの後続処理を止める
    st.stop()


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

# st.title("🍃 一茶のこころ × 浮世絵の風")

# 👇 代わりにこれを追加
st.markdown("""
<style>
/* タイトルをレスポンシブに調整 */
.responsive-title {
  font-size: clamp(20px, 5vw, 28px);  /* 幅に応じて自動調整 */
  font-weight: 600;
  text-align: center;
  white-space: nowrap;  /* 折り返し防止 */
  overflow: hidden;
  text-overflow: ellipsis;  /* はみ出した場合「…」表示 */
  margin-top: -10px;  /* 上下余白微調整（任意） */
}
</style>

<h3 class='responsive-title'>🍃 一茶のこころ × 浮世絵の風</h3>
""", unsafe_allow_html=True)


st.markdown("""
<style>
.subtext {
  text-align: center;                /* 中央寄せ */
  font-size: clamp(14px, 2.5vw, 17px);  /* スマホ対応でフォント自動調整 */
  color: #555;                       /* 落ち着いた文字色 */
  line-height: 1.6;                  /* 行間 */
  margin-top: -10px;                 /* タイトルとの距離を微調整 */
}
</style>

<div class="subtext">
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
    st.session_state.plutchik = "喜び"

st.session_state.plutchik = st.radio(
    "ステップ2: 表現したい感情を選択してください",
    ["喜び", "信頼", "恐れ", "驚き", "悲しみ", "嫌悪", "怒り", "期待"],
    index=["喜び", "信頼", "恐れ", "驚き", "悲しみ", "嫌悪", "怒り", "期待"].index(st.session_state.plutchik),
    horizontal=True
)

# ===== ステップ3: 日本的情緒を選択（フォームの外で即時更新） =====
if "aesthetic" not in st.session_state:
    st.session_state.aesthetic = "素朴"

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
# ===== グローバルCSS（ステップ見出し・フォーム余白の調整） =====
CSS_GLOBAL = """
<style>
/* ステップ見出し */
.step-label {
    font-size: 14px !important;      /* ステップ1と同じサイズ */
    font-weight: 400 !important;     /* 標準の太さ */
    margin-top: -1em !important;
    margin-bottom: -1em !important; /* ←ここを微調整 */
}

/* Streamlit の入力フォーム全般に適用 */
div[data-baseweb="input"] {
    margin-top: -2 !important;        /* 上方向のマージンを削除 */
    padding-top: 0 !important;       /* 内側の余白も削除 */
}
textarea {
    margin-top: 0 !important;
    padding-top: 0 !important;
}
</style>
"""
st.markdown(CSS_GLOBAL, unsafe_allow_html=True)

# ===== ステップ4: キーワード入力 =====
st.markdown(
    """
    <div style="margin-top: -0.8em; margin-bottom: 0.5em;">
        <p class="step-label" style="margin-top: 0 !important;">
        ステップ4: キーワード（例：川、家族、影）を入力してください
        </p>
    </div>
    <div style="margin-top: 1em; margin-bottom: -2em; color: #666; font-size: 13px; line-height: 1.5;">
        ※ 一茶の約2.2万句から検索するため、<b>「単語」入力のほうが多くの俳句がヒットします。</b><br>
        （文章を入れると条件に合う句が少なくなる場合があります）
    </div>
    """,
    unsafe_allow_html=True
)

keyword = st.text_input("", value="焼きいも")


# 💡 ステップ5だけ別クラスを使用
st.markdown(
    """
    <style>
    .step-label-5 {
        font-size: 14px !important;
        font-weight: 400 !important;
        margin-top: 1.2em !important;    /* ← ここで自由に調整OK */
        margin-bottom: -2em !important;
    }
    </style>
    <p class="step-label-5">
    ステップ5: あなたの体験・感情を入力してください
    </p>
    """,
    unsafe_allow_html=True
)

experience = st.text_area("", value="夕暮れ、道端の屋台から甘い煙が立ちのぼる。手の中の温もりが、季節の冷たさをやさしく包んだ。")

# ===== ステップ6: 擬音語優先チェック =====
prioritize_giongo = st.checkbox(
    "ステップ6: 擬音語（繰り返し表現）を優先する場合はチェックを入れてください",
    value=True
)



if st.button("ステップ7: 条件を確定（📚参照句を確定）"):
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

    # ✅ ここを追加（確定表示＋参照句へ誘導＋expander自動オープン用フラグ）
    st.session_state.just_locked_refs = True
    st.success("📚 参照条件を確定しました。下の『📚 一茶の句からAIが選んだ参照句…』をご覧ください。")
    try:
        st.toast("✅ 参照句を確定しました。下へスクロールしてご確認ください。", icon="✅")
    except Exception:
        pass  # Streamlitのバージョンでtoastがない場合は無視

# 参照句プレビュー
open_refs = bool(st.session_state.get("just_locked_refs", False))
with st.expander("📚 一茶の句からAIが選んだ参照句。🎵＝擬音語入り）", expanded=open_refs):
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

# ✅ expander表示後にフラグをリセット（毎回開きっぱなしにならないように）
if st.session_state.get("just_locked_refs"):
    st.session_state.just_locked_refs = False

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
    # Streamlitフォームでラップ（内部変更では再実行されない）
    with st.form("haiku_form"):
        submitted = st.form_submit_button("① 俳句生成", use_container_width=True)

    # ボタン押下時にだけ実行（busyフラグで多重防止）
    if submitted and not st.session_state.get("busy"):
        st.session_state["busy"] = True
        try:
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
        finally:
            st.session_state["busy"] = False  # 実行完了後に解除

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
    "下部中央": "下部中央",
    "右下": "右下",
    "左下": "左下",
    "中央": "中央",
    "右上": "右上",
    "左上": "左上",
    "上部中央": "上部中央"
}
if "pos_choice" not in st.session_state:
    st.session_state.pos_choice = "下部中央"
if "inset_pct" not in st.session_state:
    st.session_state.inset_pct = 5
if "min_bottom_px" not in st.session_state:
    st.session_state.min_bottom_px = 52
if "line_spacing" not in st.session_state:
    st.session_state.line_spacing = 1.35
if "auto_sync_layout" not in st.session_state:
    st.session_state.auto_sync_layout = True

def build_directives(haiku_en, anchor_text, inset_pct, min_bottom_px, line_spacing):
    return f"""以下の英語俳句を**既存のアートワークの中に直接配置**してください（帯・余白の追加やキャンバス拡張は禁止）。
フォントは Allura を使用し、なければ似た優雅なスクリプト体を使用してください。
改行位置はそのまま保持し、引用符や余分な文字を入れないでください：:
{haiku_en}

レイアウト条件（重要）：
- 半透明の帯や図形、新しい余白を追加しないこと。
- 詩はシーンの{anchor_text}エリアに配置すること。
- すべての端から{inset_pct}%の安全インセットを確保し、文字が端に触れたりはみ出したりしないようにする。
- テキストのベースラインを（1024×1024キャンバス上で）下端から少なくとも{min_bottom_px}px上に保つこと。
- 文字が切れる可能性がある場合は、自動的にフォントサイズを小さくし、行間を約{line_spacing}倍にする。
- 読みやすさのために控えめな影または細い縁取りを適用するが、目立ちすぎないようにする。
- 浮世絵の雰囲気を損なわないよう、テキスト配置以外の要素は変更しないこと。
- 最終出力は必ず1024×1024にすること。"""

# 初期のレイアウト指示
if "remix_directives_area" not in st.session_state:
    st.session_state.remix_directives_area = build_directives(
        haiku_en,
        st.session_state.pos_choice,  # ← ここを直接渡す
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
    
    # --- ラジオの初期化 ---
    if "pos_choice" not in st.session_state:
        st.session_state.pos_choice = "下部中央"
    
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
        choice = st.radio(  # ←ここを1段下げる
            "文字の配置（画像内）",
            options,
            key="pos_choice",
            horizontal=True
        )
    
    # --- checkboxの初期化（1回だけTrue）---
    if "auto_sync_layout__inited" not in st.session_state:
        st.session_state.auto_sync_layout = True   # 既定ON
        st.session_state.auto_sync_layout__inited = True
    
    st.checkbox(
        "配置変更に合わせてレイアウト指示を自動更新する",
        key="auto_sync_layout",
        value=st.session_state.auto_sync_layout
    )


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
