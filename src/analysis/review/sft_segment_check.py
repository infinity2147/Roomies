"""Check build_dataset.render_segment against the real per-call prompts in a capture file:
each call's vLLM prompt (generation prompt incl.) must be a token prefix of the training sequence
(modulo the trailing empty-thought), the next token must be trained, and nothing inside tool
outputs may be trained."""
import json, sys
from transformers import AutoTokenizer
from src.sft.format import MODEL, EMPTY_THOUGHT, to_template_msgs
from src.sft.build_dataset import segments, render_segment
tok = AutoTokenizer.from_pretrained(MODEL)
calls = [json.loads(l) for l in open(sys.argv[1])]
calls = [c for c in calls if c.get("status") == 200 and "response" in c]
calls.sort(key=lambda c: c["t"])
segs = segments(calls)
print("calls", len(calls), "segments", len(segs), [len(s) for s in segs])
for si, seg in enumerate(segs):
    ids, mask = render_segment(seg, tok)
    ok_prefix = ok_start = had_et = 0
    for c in seg:
        tools = c["request"].get("tools")
        p = tok.apply_chat_template(to_template_msgs(c["request"]["messages"]), add_generation_prompt=True, tokenize=False, tools=tools, enable_thinking=False)
        if p.endswith(EMPTY_THOUGHT):
            had_et += 1; p = p[: -len(EMPTY_THOUGHT)]
        pid = tok(p, add_special_tokens=False)["input_ids"]
        if ids[: len(pid)] == pid:
            ok_prefix += 1
            ok_start += int(len(pid) < len(mask) and mask[len(pid)] == 1)
    # trained text audit
    trained = tok.decode([t for t, m in zip(ids, mask) if m], skip_special_tokens=False)
    tr_resp_markers = trained.count("<|tool_response>"); tr_resp_close = trained.count("<tool_response|>")
    print(f"seg {si}: calls={len(seg)} tokens={len(ids)} trained={sum(mask)} prefix_ok={ok_prefix}/{len(seg)} "
          f"gen_starts_trained={ok_start}/{len(seg)} prompts_with_empty_thought={had_et} "
          f"trained '<|tool_response>'={tr_resp_markers} trained '<tool_response|>'(tool output close)={tr_resp_close} "
          f"trained '<turn|>'={trained.count('<turn|>')}")
    # print last trained chunk ends
    spans=[]; cur=[]
    for t,m in zip(ids,mask):
        if m: cur.append(t)
        elif cur: spans.append(cur); cur=[]
    if cur: spans.append(cur)
    print("   span ends:", [tok.decode(s[-3:], skip_special_tokens=False) for s in spans[:3]], "...", [tok.decode(s[-3:], skip_special_tokens=False) for s in spans[-2:]])
