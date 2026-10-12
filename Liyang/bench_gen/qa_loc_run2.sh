cd /workspace/work/ls/wt-gen/bench_gen
export QA_BUDGET=0.98
python3 qa_loc.py gen v1
python3 qa_loc.py gen oracle & python3 qa_loc.py gen closed & wait
python3 qa_loc.py gen oracle; python3 qa_loc.py gen closed
echo GENDONE
