cd /workspace/work/ls/wt-gen/bench_gen
export QA_BUDGET=0.98
s=$(date +%s.%N); LINGSHU_PROMPT_LAYOUT=legacy python3 qa_loc.py judge J1 > /dev/null; e=$(date +%s.%N); echo "TIME J1_legacy_rerun $s $e"
s=$(date +%s.%N); LINGSHU_PROMPT_LAYOUT=prefix python3 qa_loc.py judge J3; e=$(date +%s.%N); echo "TIME J3_prefix $s $e"
s=$(date +%s.%N); LINGSHU_PROMPT_LAYOUT=prefix python3 qa_loc.py judge J3; e=$(date +%s.%N); echo "TIME J3_prefix_rerun $s $e"
echo LLMBENCHDONE
