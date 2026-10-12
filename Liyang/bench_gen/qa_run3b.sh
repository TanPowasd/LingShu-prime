#!/bin/sh
cd "$(dirname "$0")"
python3 qa_lme.py gen v1@sess lme_test
python3 qa_lme.py judge lme_test J1
python3 qa_lme.py judge lme_test J2
python3 qa_lme.py score lme_test J1 > qa/score_lme_test.txt
python3 qa_lme.py score lme_test J2 > qa/score_lme_test_J2.txt
echo QA3DONE
