
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
        # ── 空・天候・光 ──
        "evening squall over rice paddies", "drizzle under paper umbrellas", "sudden downpour with gusting wind",
        "rainbow after storm over village", "low winter sun casting long shadows", "hazy spring dawn over fields",
        "morning fog drifting across river", "glow of sunset behind distant hills", "stars faint over quiet bay",
        "first frost shimmering on grass", "thin crescent moon above shoreline", "mist lifting from cedar forest",
    
        # ── 水辺・海・川 ──
        "boats moored at a quiet inlet", "ferry crossing slow broad river", "cormorant fishing at night with torch",
        "waves cresting against rocky coast", "tidal flats with people gathering shells", "seaweed drying on wooden racks",
        "quiet canal reflecting willows", "carp circling in a garden pond", "salt fields glistening under sun",
    
        # ── 山・野・道（山だけに偏らない要素多め）──
        "terraced rice fields layered like steps", "footpath winding through tea plantations",
        "country road lined with thatched hedges", "stone milestone on an old post road",
        "wind through tall pampas grass", "persimmon trees heavy with fruit", "scarecrow standing in harvested field",
        "cedar avenue leading to a distant shrine", "bamboo grove whispering in afternoon breeze",
        "mossy stepping stones after rain",
    
        # ── 集落・建物・暮らし ──
        "thatched farmhouse with smoking hearth", "paper lanterns at a rustic wayside tea house",
        "engawa veranda with shoji glow", "woodcutters stacking fresh logs", "women rinsing cloth at river shallows",
        "rice sheaves drying on racks", "charcoal burners’ hut at forest edge", "sake brewery barrels by roadside",
        "street market at early morning", "silk cocoons drying on trays",
    
        # ── 季の行事・道具 ──
        "fireworks over summer river", "dragonfly kites in high wind", "children spinning tops on packed earth",
        "paper wind chimes tinkling at eaves", "straw raincoats and sedge hats hung to dry", "bonfire of fallen leaves",
        "mochi pounding with wooden mallets", "chestnuts roasting over a brazier", "New Year pine decorations at gate",
    
        # ── 樹木・花 ──
        "plum blossoms by a rustic gate", "cherry petals drifting along stream", "red maples arching over path",
        "camellias blooming in winter shade", "wild chrysanthemums by stone wall", "lotus leaves spreading on quiet pond",
    
        # ── 鳥獣・生き物 ──
        "swallows darting under the eaves", "sparrows perched on reed stalks", "herons standing in shallow water",
        "wild geese flying south in V-shape", "deer beneath autumn maples", "fox slipping along the roadside",
        "monkeys chattering in chestnut trees", "fireflies floating over stream", "dragonflies skimming paddy water",
        "cranes gliding over tidal shallows",
    
        # ── 旅・人の動き ──
        "pilgrims passing with walking staves", "palanquin bearers resting by pine",
        "porters crossing a shallow ford", "fishermen mending nets on the shore", "itinerant monk in straw hat playing flute",
        "mail runner speeding along post road",
    
        # ── 既存の人気モチーフ（頻度を下げるなら後方に）──
        "Mount Fuji in distance", "bridge seen from afar in morning mist",
        "mountain village under falling snow"
    ]

    motif = random.choice(ukiyo_elements)

    prompt = f"""IMPORTANT: The main subject must be the landscape itself, not people.
Humans, if included, appear as tiny silhouettes far away (less than 3% of image height, under 1/25 of total area).
Masterpiece in the style of Utagawa Hiroshige (1797–1858),
renowned for poetic landscapes and dramatic perspective.
Edo-period {season_en} ukiyo-e woodblock print.
Haiku: {haiku_ja}
Explanation: {explanation_ja}
Keyword (seasonal word or theme): {keyword}
{aesthetic_line}- Composition: sweeping landscape fills the majority of the frame.
  Humans or animals should appear extremely small and distant—tiny silhouettes—
  emphasizing the vastness of nature. 
  Use dynamic diagonal layout and deep atmospheric perspective, in the manner of Utagawa Hiroshige’s landscapes.
  The horizon and flowing elements (rivers, hills, bridges, or coastlines) should draw the viewer’s eye into the distance.

- Mood: calm, poetic, and vast; evoke serenity and awe before nature’s scale.
  The presence of human life is felt only faintly, not seen closely.

- Technique: depict people as distant travelers or tiny silhouettes that harmonize with the scenery.
  Apply Hiroshige’s signature indigo (Prussian blue) gradients and fading tones toward the horizon.
  Mimic woodblock textures and clean linework; preserve generous negative space.
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
