#!/bin/bash
for p in $(pgrep -f "run_loo[p]"); do kill $p; done
for p in $(pgrep -f "harness.ru[n] --plugin (null|bm25)"); do kill $p; done
