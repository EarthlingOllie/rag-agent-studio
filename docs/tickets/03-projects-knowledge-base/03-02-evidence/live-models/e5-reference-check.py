"""Reference: multilingual-e5-small via transformers (safetensors) vs the app's LocalEmbedder."""
import asyncio, torch, torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer
from app.embeddings.local import LocalEmbedder
texts = ["query: How much holiday do I get?", "passage: Everyone gets 25 days of annual leave.", "passage: Claim expenses within 30 days.",
         "query: How many days of annual leave do I get?", "query: How long do I have to claim expenses?"]
tok = AutoTokenizer.from_pretrained("intfloat/multilingual-e5-small"); m = AutoModel.from_pretrained("intfloat/multilingual-e5-small")
b = tok(texts, padding=True, truncation=True, return_tensors="pt")
with torch.no_grad(): out = m(**b).last_hidden_state
mask = b["attention_mask"][..., None]; ref = F.normalize((out*mask).sum(1)/mask.sum(1), dim=-1)
e = LocalEmbedder()
async def go():
    p = await e.embed_passages([t.removeprefix("passage: ") for t in texts[1:3]])
    q = [await e.embed_query(t.removeprefix("query: ")) for t in (texts[0], texts[3], texts[4])]
    return q[0], p[0], p[1], q[1], q[2]
app = torch.tensor(asyncio.run(go()))
print("max abs diff app vs reference:", (app-ref).abs().max().item())
s = ref @ ref.T
print("reference cos(q_holiday, leave)=%.4f cos(q_holiday, expenses)=%.4f" % (s[0,1], s[0,2]))
print("reference cos(q_leave, leave)=%.4f cos(q_leave, expenses)=%.4f" % (s[3,1], s[3,2]))
print("reference cos(q_expenses, leave)=%.4f cos(q_expenses, expenses)=%.4f" % (s[4,1], s[4,2]))
