# E0 — SFT formatting (2026-10-02)

- Wire format captured with `src/sft/capture_proxy.py` (frozen scaffold C6a): system (our instruction + ADK agent-identity + skill-toolset text), harness user prompt, assistant `tool_calls` (JSON-string args), `tool` messages (JSON tool output); 12 tools (`src/sft/tools_c6a.json`); `enable_thinking=false`, max_completion_tokens 6144, temperature 0.3.
- vLLM converts tool-call argument strings to dicts before templating (`_postprocess_messages`); we do the same → native `<|tool_call>call:name{k:<|"|>v<|"|>}<tool_call|>`.
- Stop tokens: after tool calls the model emits `<|tool_response>` (id 50); text answers end with `<turn|>` (106). Both are in the loss mask.
- With thinking off the very first generation of a model turn sees `<|channel>thought\n<channel|>` (3 tokens) that history renders never contain; training sequences use the history format (exact for every other turn).
- Round trip on a captured run (requests_7433): 15/16 vLLM prompts are exact token prefixes of the training sequence; all 16 assistant spans trained; vLLM `gemma4` tool parser recovers the original calls from the trained spans.
- Long runs are compacted by ADK (threshold 14,336 tokens): 35/46 passing pilot trajectories exceed it, so traces ≠ what the model saw. **Training data comes from capture.jsonl** (exact per-call prompts), segmented at compaction boundaries (`src/sft/build_dataset.py`). Kaggle eval kernels now run the capture proxy in-process.
