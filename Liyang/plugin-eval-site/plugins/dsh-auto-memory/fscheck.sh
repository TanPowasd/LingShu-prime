#!/usr/bin/env bash
# 读盘完整性检查：逐文件 timeout 3 s 全量读取，列出读不出的文件（沙箱重启后工作区盘曾出现 EIO）。
cd "$1" || exit 2
n=0; bad=0
while IFS= read -r f; do
  n=$((n+1))
  if ! timeout 3 cat "$f" > /dev/null 2>&1; then bad=$((bad+1)); echo "BAD $f"; fi
done < <(find . -type f)
echo "checked $n bad $bad"
