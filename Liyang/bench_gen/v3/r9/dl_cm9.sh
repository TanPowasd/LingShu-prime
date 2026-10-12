#!/bin/bash
# r9：下载 ConvoMem batched_038/039 五个类别（同 H-CM 目录）→ H-CM9
cd /workspace/work/ls/_shared/convomem
B=https://huggingface.co/datasets/Salesforce/ConvoMem/resolve/main/core_benchmark/pre_mixed_testcases
for b in 039 038; do
 for p in "ue1 user_evidence/1_evidence" "ue2 user_evidence/2_evidence" "af1 assistant_facts_evidence/1_evidence" "pe1 preference_evidence/1_evidence" "ic2 implicit_connection_evidence/2_evidence"; do set -- $p
  [ -s ${1}_$b.json ] || curl -sL --retry 3 -o ${1}_$b.json.part "$B/$2/batched_$b.json" && mv -f ${1}_$b.json.part ${1}_$b.json 2>/dev/null
  echo "$(date +%T) $1_$b $(stat -c %s ${1}_$b.json)"
 done
done
echo DLDONE
