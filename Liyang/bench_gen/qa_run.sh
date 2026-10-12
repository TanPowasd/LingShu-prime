#!/bin/sh
cd "$(dirname "$0")"
for a in base v1 oracle closed; do python3 qa_lme.py gen $a lme_test; done
while ! grep -q ALLDONE runs_resume.log 2>/dev/null; do sleep 20; done
python3 qa_lme.py gen v1-noctx lme_test
python3 qa_lme.py judge lme_test
python3 qa_lme.py score lme_test > qa/score_lme_test.txt
echo QADONE
