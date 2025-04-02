#!/bin/bash

OUTPUT_FILE="/home/ubuntu/speedtest/output.csv"
SERVER_ID="48463"

# 日時部分を取得 (改行なし)
# dateの出力には改行が付くので tr で削除
datetime_part=$(TZ='Asia/Tokyo' /usr/bin/date +'"%Y-%m-%d %H:%M:%S",' | /usr/bin/tr -d '\n')

# speedtest部分を取得
# エラー出力を抑制したい場合は 2>/dev/null を追加検討
speedtest_part=$(/home/ubuntu/speedtest/speedtest --server-id="$SERVER_ID" --format=csv)

# 日時とspeedtest結果を連結してファイルに追記
# printf を使うと改行を確実に制御できる (%s の後に \n を追加)
printf "%s%s\n" "$datetime_part" "$speedtest_part" >> "$OUTPUT_FILE"

exit 0
