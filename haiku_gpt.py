

# ===== haiku_gpt.py SAFE HEADER =====
import os
import time
import random
import logging
import json
import re



from openai import OpenAI
from openai import RateLimitError, APIStatusError
_call_seq = 0
def _bump_call_seq(tag: str):
    # 各呼び出しの通番を出す
    import time, logging
    global _call_seq
    _call_seq += 1
    logging.warning("[CALL %04d] %s t=%.3f", _call_seq, tag, time.time())


logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")

_client = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            max_retries=0,
            timeout=60,
        )
        key = os.getenv("OPENAI_API_KEY")
        logging.warning(f"OPENAI_API_KEY head={key[:5]+'…' if key else 'None'}")
    return _client

def _with_backoff(callable_fn, *, max_attempts=3, base=0.8, cap=8.0):
    import time, random, logging
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            return callable_fn()
        except Exception as e:
            last_err = e
            # 共通的に status / headers / body を引き抜く
            status = getattr(e, "status_code", None)
            headers = None
            body_text = None
            req_id = None
            try:
                resp = getattr(e, "response", None)
                if resp is not None:
                    headers = dict(getattr(resp, "headers", {}) or {})
                    body_text = getattr(resp, "text", None)
                    req_id = headers.get("x-request-id")
            except Exception:
                pass
            logging.error(
                "[ERR TRY %d/%d] type=%s status=%s req_id=%s headers=%s body=%s",
                attempt, max_attempts, e.__class__.__name__, status, req_id, headers, body_text
            )
            # 429/5xx のときだけ再試行
            if status not in (429, 500, 502, 503, 504):
                raise
        if attempt < max_attempts:
            sleep = min(cap, base * (2 ** (attempt - 1))) * (0.5 + random.random())
            logging.warning("Retrying after %.2fs …", sleep)
            time.sleep(sleep)
    raise last_err


# ===== /SAFE HEADER =====
def _diag_probe_once():
    """
    小さなリクエストを1回だけ送り、レート制限ヘッダをログに出す診断用。
    本番処理には影響しない。
    """
    import logging
    client = _get_client()
    # with_raw_response で headers を取得
    raw = client.with_raw_response.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role":"system","content":"You are a helpful assistant."},
            {"role":"user","content":"Say 'pong'."},
        ],
        max_tokens=5,
        temperature=0.0,
    )
    logging.warning("[DIAG] status=%s headers=%s", raw.status_code, dict(raw.headers or {}))
    resp = raw.parse()
    logging.warning("[DIAG] content=%s", resp.choices[0].message.content.strip())



def call_gpt_haiku(payload: dict, max_retries: int = 5) -> dict:
    _bump_call_seq("call_gpt_haiku")
    logging.warning("[CALL] call_gpt_haiku invoked")
    """新作俳句＋意訳＋参照理由をJSONで返す。"""
    client = _get_client()
    refs = payload.get('references', [])
    refs_numbered = "\n".join([f"{i+1}. {r.get('text','')} | 出典: {r.get('source','')}" for i, r in enumerate(refs)])


    system_prompt = """あなたは「小林一茶 × 新作俳句 × 参照句運用」の専門家です。
以下のJSONだけを出力してください（余文・解説・前置き禁止）：
{
  "haiku_ja": "五七五の新作（日本語）",
  "explanation_ja": "日本語の意訳・背景（100-200字）",
  "reasons_refs_ja": "結論ファースト1文＋改行＋(1)(2)(3)をMarkdown箇条書き形式（- (1) ... の形）で出力する。形式例:『【結論】...\\n- (1) ...\\n- (2) ...\\n- (3) ...』"
  "references_numbered": "1. 〇〇 | 出典: △△ (年)\\n2. 〇〇 | 出典: △△ (年)\\n3. 〇〇 | 出典: △△ (年)"
}
厳守事項：
- 必ず命を懸けて5音・7音・5音の構成にする（合計17モーラ）
- 5音 7音 5音とスペースで5音 7音 5音を区切って表示する
- モーラ数は、ゃゅょ→1モーラ、っ→1モーラ、ん→1モーラ、長音（ー）→1モーラとして数える
- 記号・英語・ルビ・句読点・解説は出力しない（俳句のみ）
- 文末は名詞・体言止め可、助詞で終わっても良い
-自己チェックを以下3点実行してください
1) ひらがなに内部変換してモーラを数える（出力には見せない）
2) 5-7-5になっていなければ即座に言い換えて再生成
3) 最終出力は俳句3行のみ
- 自然と感情をテーマにする
- 選択された感情（plutchik）と日本的情緒（aesthetic）を句の内容または語感に必ず反映すること。   
- 必ず参照句を活用して新作俳句を作成してください
- 小林一茶らしさである、擬音語活用については参照句をして生かしてください。
- 小動物への愛についても参照句を生かしてください。
- 参照句の文末を似せてください。
- 参照句(1)(2)(3)の具体要素（語／音象徴／構図）を最低1つずつ反映すること
- JSON以外は出力しない。
- 「理由」は“参照俳句の選定理由”。文頭を『この句は』で始めない。
- 「reasons_refs_ja」は必ず『【結論】』で始め、次行以降に(1)(2)(3)を改行で並べる。
- 各(1)(2)(3)では、参照句の具体要素（構造/リズム/テーマ/語感 等）と、新作への変奏を簡潔に述べる。
- **参照句に擬音語（繰り返し表現 🎵）が含まれる場合、そのリズムや響きを新作でどう活かしたかを必ず書く。**
- 「意訳」は俳句の情景と感情のみ（参照句の話は書かない）。日本的情緒を1つ以上含める。
- 固有名詞や現代語過多を避け、一茶らしい素朴さと生命へのまなざしを重視。

"""

    user_prompt = f"""入力条件：
season = {payload.get('season')}
plutchik = {payload.get('plutchik')}
aesthetic = {payload.get('aesthetic')}
keyword = {payload.get('keyword')}
experience = {payload.get('experience')}

参照俳句（必ず(1)(2)(3)で言及）:
{refs_numbered}
"""
    sp_len = len(system_prompt)
    up_len = len(user_prompt)
    logging.warning("[PROMPT] system=%d chars, user=%d chars, total=%d", sp_len, up_len, sp_len+up_len)

    # 🧩 API呼び出し部（ここを新しく）
    def _api_call():
        return client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
            max_tokens=220,
        )

    resp = _with_backoff(_api_call)
    
    content = resp.choices[0].message.content
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        s = content.strip()
        if s.startswith("```"):
            s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
            s = re.sub(r"\n?```$", "", s)
        start = s.find("{"); end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start:end+1]
        s = s.replace("“", '"').replace("”", '"').replace("’", "'")
        s = re.sub(r",(\s*[\]}])", r"\1", s)
        s = re.sub(r"'([A-Za-z0-9_]+)'\s*:", r'"\1":', s)
        s = re.sub(r":\s*'([^']*)'", lambda m: ':"{}"'.format(m.group(1).replace('"', '\\"')), s)
        try:
            data = json.loads(s)
        except json.JSONDecodeError:
            data = {"haiku_ja": "", "explanation_ja": "", "reasons_refs_ja": "", "references_numbered": refs_numbered}

    for k in ["haiku_ja", "explanation_ja", "reasons_refs_ja", "references_numbered"]:
        data.setdefault(k, "")
    return data

def generate_english_tweet_block(haiku_ja: str, explanation_ja: str) -> str:
    """日本語俳句＋説明から X 向け英語ブロックを生成"""
    client = _get_client()
    system_prompt = """あなたは「俳句英訳 × X（Twitter）投稿整形」の専門家です。
次の4ブロックだけを出力：
🌿 俳句（日本語）

{haiku_ja}

🍃 Haiku (English)

{haiku_en_3lines}

✨ Explanation

{explanation_en_short}

制約：合計280字以内。英訳は3行、説明は1-2文。絵文字は🌿🍃✨のみ。"""

    user_prompt = f"""俳句（日本語）:
{haiku_ja}

俳句の説明（日本語の意訳/背景の要点）:
{explanation_ja}
"""
    client = _get_client()

    # ✅ ここから“関数の中”に置くこと（トップレベルに出さない）
    def _api_call():
        return client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
            max_tokens=220,
        )

    try:
        resp = _with_backoff(_api_call)
    except Exception:
        logging.exception("[call_gpt_haiku] failed")
        raise

