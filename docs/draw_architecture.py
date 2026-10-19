"""Draws docs/architecture.png with Pillow.  Usage: python docs/draw_architecture.py"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIR = "/usr/share/fonts/truetype/dejavu/"
W, H = 1800, 1120
img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)


def font(size, bold=False):
    try:
        return ImageFont.truetype(FONT_DIR + ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"), size)
    except OSError:
        return ImageFont.load_default()


INK, MUTED = "#1f2933", "#52606d"
BLUE, BLUE_BG = "#2563eb", "#eaf1ff"
GREEN, GREEN_BG = "#15803d", "#e8f6ec"
AMBER, AMBER_BG = "#b45309", "#fff4e0"
RED, RED_BG = "#b91c1c", "#fdecec"
GRAY_BG = "#f3f4f6"


def box(x, y, w, h, title, lines=(), fill=GRAY_BG, edge=INK, title_size=20):
    d.rounded_rectangle([x, y, x + w, y + h], radius=12, fill=fill, outline=edge, width=2)
    d.text((x + 14, y + 10), title, fill=INK, font=font(title_size, True))
    for i, line in enumerate(lines):
        d.text((x + 14, y + 40 + i * 24), line, fill=MUTED, font=font(16))


def container(x, y, w, h, label, edge, fill):
    d.rounded_rectangle([x, y, x + w, y + h], radius=16, fill=fill, outline=edge, width=3)
    d.text((x + 16, y + 10), label, fill=edge, font=font(22, True))


def arrow(points, color=INK, label=None, label_pos=None):
    d.line(points, fill=color, width=3)
    (x1, y1), (x2, y2) = points[-2], points[-1]
    if x1 == x2:
        s = 1 if y2 > y1 else -1
        head = [(x2, y2), (x2 - 9, y2 - 16 * s), (x2 + 9, y2 - 16 * s)]
    else:
        s = 1 if x2 > x1 else -1
        head = [(x2, y2), (x2 - 16 * s, y2 - 9), (x2 - 16 * s, y2 + 9)]
    d.polygon(head, fill=color)
    if label:
        d.text(label_pos, label, fill=color, font=font(15, True))


d.text((40, 24), "Guardrail architecture: HIT student-services assistant", fill=INK, font=font(30, True))

# ---- Row 1: input side
box(40, 150, 210, 110, "User message", ["free text from", "a student"], fill="white")
container(300, 90, 820, 300, "INPUT GUARDRAILS (run on every request)", BLUE, BLUE_BG)
box(325, 140, 245, 220, "1 PII detection", ["regex + Luhn + context", "keywords", "", "action: redact to", "[EMAIL], [PHONE] ...", "+ notice to user"], fill="white", edge=BLUE)
box(590, 140, 245, 220, "2 Prompt injection", ["normalise (NFKC, leet,", "zero-width), weighted", "pattern bank, base64", "decode; score >= 0.6", "action: block"], fill="white", edge=BLUE)
box(855, 140, 245, 220, "3 Sensitive topic", ["keyword classifier ->", "policy table:", "self-harm: escalate", "violence: block", "misconduct: refuse", "medical/legal/harass:", "  add disclaimer"], fill="white", edge=BLUE)
box(1180, 165, 200, 170, "Policy gate", ["injection? block", "topic stops?", "  escalate/block/", "  refuse", "else continue"], fill=AMBER_BG, edge=AMBER)
box(1440, 150, 320, 200, "Safe canned reply", ["blocked / escalated /", "refused message.", "Model is never called,", "so nothing unsafe can", "be generated."], fill=RED_BG, edge=RED)

arrow([(250, 205), (300, 205)])
arrow([(1120, 250), (1180, 250)])
arrow([(1380, 250), (1440, 250)], RED, "stop", (1386, 218))

# ---- Row 2: model and output side
box(40, 520, 230, 150, "Retriever", ["top-2 documents", "from knowledge base", "(KB-001..KB-008)"], fill=GREEN_BG, edge=GREEN)
box(320, 520, 230, 150, "LLM", ["mock (default) or", "Claude via API;", "must return JSON"], fill=GREEN_BG, edge=GREEN)
container(600, 450, 900, 330, "OUTPUT GUARDRAILS", BLUE, BLUE_BG)
box(625, 500, 200, 250, "4 Schema", ["Pydantic model:", "answer, sources,", "confidence 0-1,", "status; sources", "must be retrieved", "", "invalid: retry once,", "then fallback"], fill="white", edge=BLUE, title_size=19)
box(845, 500, 200, 250, "5 Sensitive info", ["PII (allowlist for", "public contacts),", "API keys, tokens,", "canary token", "", "secret/canary:", "  fallback", "PII: redact"], fill="white", edge=BLUE, title_size=19)
box(1065, 500, 200, 250, "6 Groundedness", ["each claim vs.", "source sentences:", ">= 60% word overlap", "and all numbers", "present", "", "some bad: trim", "all bad: fallback"], fill="white", edge=BLUE, title_size=19)
box(1285, 500, 195, 250, "7 Final redact", ["PII check again", "on the trimmed", "answer before", "it is returned"], fill="white", edge=BLUE, title_size=19)
box(1540, 520, 220, 160, "Response", ["answer + notices", "(PII removed,", "trimmed, disclaimer)"], fill=GREEN_BG, edge=GREEN)
box(1540, 820, 220, 140, "Safe fallback", ["\"couldn't produce", "a reliable answer;", "contact Registrar\""], fill=RED_BG, edge=RED)

arrow([(1280, 335), (1280, 420), (155, 420), (155, 520)], INK, "continue (redacted text)", (170, 392))
arrow([(270, 595), (320, 595)])
arrow([(550, 595), (600, 595)])
arrow([(825, 625), (845, 625)])
arrow([(1045, 625), (1065, 625)])
arrow([(1265, 625), (1285, 625)])
arrow([(1500, 600), (1540, 600)], GREEN)
arrow([(1150, 780), (1150, 890), (1540, 890)], RED, "invalid after retry / leak / no supported claims", (900, 900))
d.line([(725, 780), (725, 890), (1150, 890)], fill=RED, width=3)
d.line([(945, 780), (945, 890)], fill=RED, width=3)
# retry loop from schema back to the LLM
arrow([(650, 780), (650, 820), (435, 820), (435, 670)], AMBER, "retry once (schema invalid)", (445, 828))

# ---- Audit trail
box(40, 990, 1460, 100, "Audit trace (every request)",
    ["Each guardrail returns GuardrailResult(flagged, action, reason, details). The full trace is kept in AssistantReply.results;",
     "evaluate.py writes it to results/traces.json for review."], fill=GRAY_BG)

out = Path(__file__).with_name("architecture.png")
img.save(out)
print("saved", out)
