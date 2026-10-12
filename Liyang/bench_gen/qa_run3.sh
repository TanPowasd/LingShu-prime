#!/bin/sh
cd "$(dirname "$0")"
for a in base@sess v1@sess; do python3 qa_lme.py gen $a lme_test; python3 qa_lme.py gen $a lme_test; done
python3 qa_lme.py judge lme_test J1
python3 qa_lme.py judge lme_test J2
python3 qa_lme.py score lme_test J1 > qa/score_lme_test.txt
python3 qa_lme.py score lme_test J2 > qa/score_lme_test_J2.txt
echo QA3DONE
