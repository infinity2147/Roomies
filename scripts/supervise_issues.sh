#!/usr/bin/env bash
# Keep the local vLLM server + synthetic-issue generator alive until all issues exist.
# Restarts the server when the engine dies (PP mode is occasionally flaky) and resumes generation.
cd "$(dirname "$0")/.."
total=$(wc -l < data/derived/synth_mutations.jsonl)
while true; do
  done_n=$(wc -l < data/derived/synth_issues.jsonl 2>/dev/null || echo 0)
  if (( done_n >= total )); then echo "$(date +%T) all $total issues done"; exit 0; fi
  if ! timeout 60 curl -sf -m 50 http://127.0.0.1:8011/v1/chat/completions -H 'Content-Type: application/json' \
       -d '{"model":"gemma-4-31b-it-qat-w4a16-ct","messages":[{"role":"user","content":"ok"}],"max_tokens":2}' >/dev/null; then
    echo "$(date +%T) server unhealthy -> restart"
    until scripts/start_server.sh; do echo "$(date +%T) start failed, retry in 5 min"; sleep 300; done
  fi
  echo "$(date +%T) generating ($done_n/$total done)"
  .venv/bin/python -m src.synth.issue >> results/synth_issue.log 2>&1
  sleep 10
done
