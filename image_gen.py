
from __future__ import annotations
import os, base64
from io import BytesIO
from datetime import datetime
from pathlib import Path
from PIL import Image
from openai import OpenAI

_client = None
def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client

def build_image_prompt(haiku_ja: str, explanation_ja: str, season: str, keyword: str, aesthetic: str) -> str:
    import random
    season_en = {"春":"spring","夏":"summer","秋":"autumn","冬":"winter","新年":"new year","無季":"seasonless"}.get(season,"seasonal")
    aesthetic_line = "" if aesthetic == "スキップ" else f"Japanese aesthetic: {aesthetic}\n"
    ukiyo_elements = [
        "pine trees swaying in wind","Mount Fuji in distance","boats on calm river","cranes flying above water",
        "cherry blossoms falling","moon over still pond","paper lanterns glowing at dusk","snow on rooftops",
        "farmers planting rice","autumn rice fields with golden ears","bamboo forest in wind","willow branches over river",
        "waves crashing on shore","misty mountain path","plum blossoms near gate","wild geese flying south",
        "fireflies over stream","sunrise over sea","evening bell near temple","deer in autumn forest",
        "fishermen pulling nets","tea house by the roadside","torches lighting a festival","herons standing in shallow water",
        "wind blowing through pampas grass","children playing with kites","woman hanging laundry in breeze",
        "path lined with red maple trees","bridge seen from afar in morning mist","mountain village under falling snow"
    ]
    motif = random.choice(ukiyo_elements)

    prompt = f"""Utagawa Hiroshige style ukiyo-e, Edo-period {season_en}.
Haiku: {haiku_ja}
Explanation: {explanation_ja}
Keyword (seasonal word or theme): {keyword}
{aesthetic_line}- Composition: vast nature as main subject; small human/animal figures (<=1/10 of scene); avoid bridges and torii gates; include {motif}.
- Colors: indigo gradients (aizuri-e), soft browns/greens, washi paper texture; subtle gold accents if sunlight/dawn.
- Mood: poetic, tranquil, simple. Reflect "yugen", "sabi", "aware".
- Aspect ratio: square (1:1) for NFT format.
- Strict bans: no text, no Western realism, no oil painting, no 3D, no modern objects, no close-up bridges or torii gates.
"""
    tail = {
        "侘び": "Emphasize muted tones, plain forms, and generous negative space.",
        "寂び": "Suggest patina and weathered textures, gentle fading at edges.",
        "幽玄": "Use layered haze and softened contours to hint unseen depth.",
        "もののあはれ": "Let fading light and falling leaves imply transience.",
        "風雅": "Aim for refined balance and dignified spacing; gentle hint of gold.",
        "無常": "Render subtle shifts of light and thin clouds to evoke impermanence.",
        "愛らしさ": "Include tiny animals or children naturally, never as main focus.",
        "素朴": "Keep forms simple and avoid ornate patterns.",
        "滑稽": "Allow a slight, poetic twist in pose or placement.",
        "淡白": "Reduce brushstrokes; leave wide calm surfaces.",
        "静寂": "Minimize motion; widen sky/water/snow planes.",
        "余情": "Leave fragments and do not narrate all details."
    }
    if aesthetic in tail:
        prompt += f"\n- Aesthetic nuance: {tail[aesthetic]}\n"
    return prompt

def generate_image(prompt_text: str, size: str = "1024x1024") -> Image.Image:
    client = _get_client()
    resp = client.images.generate(model="gpt-image-1", prompt=prompt_text, size=size, n=1)
    b64 = resp.data[0].b64_json
    img_bytes = base64.b64decode(b64)
    return Image.open(BytesIO(img_bytes))

def save_artifacts(img: Image.Image, meta: dict, output_dir: Path | None = None) -> dict:
    output_dir = output_dir or Path("outputs")
    output_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    png_path = output_dir / f"haiku_image_{ts}.png"
    json_path = output_dir / f"haiku_meta_{ts}.json"
    img.save(png_path, "PNG")
    json_path.write_text(__import__("json").dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"png": str(png_path), "json": str(json_path)}

# ==== 追加: 既存画像を英語俳句入りで再出力する関数 =====================

# image_gen.py
import io, base64, os, requests
from PIL import Image
from openai import OpenAI

# 既存の _get_client() がある前提

def edit_image_with_text(base_img: Image.Image, prompt: str, size: str = "1024x1024") -> Image.Image:
    """
    gpt-image-1 で既存画像を編集。まず SDK の images.edit を試し、
    未サポートなら /v1/images/edits を HTTP でフォールバック。
    """
    buf = io.BytesIO()
    base_img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    # 1) SDK で try（images.edit がある環境）
    client = _get_client()
    if hasattr(client.images, "edit"):
        try:
            resp = client.images.edit(
                model="gpt-image-1",
                image=png_bytes,        # bytes を渡せる SDK ではこれでOK
                prompt=prompt,
                size=size,
            )
            b64 = resp.data[0].b64_json
            return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
        except Exception:
            pass  # 失敗時は HTTP にフォールバック

    # 2) フォールバック：HTTP 直叩き（どの環境でも動く）
    api_key = os.getenv("OPENAI_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {
        "image": ("image.png", png_bytes, "image/png"),
    }
    data = {
        "model": "gpt-image-1",
        "prompt": prompt,
        "size": size,
        # 必要なら "quality": "high", "input_fidelity": "low" などを追加
    }
    r = requests.post("https://api.openai.com/v1/images/edits", headers=headers, files=files, data=data, timeout=90)
    r.raise_for_status()
    out_b64 = r.json()["data"][0]["b64_json"]
    return Image.open(io.BytesIO(base64.b64decode(out_b64))).convert("RGB")
