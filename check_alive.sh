FILE_PATH="./alive"
CURRENT_TIME=$(date +%s)
FILE_MODIFICATION_TIME=$(stat -c %Y $FILE_PATH)
TIME_DIFF=$((CURRENT_TIME - FILE_MODIFICATION_TIME))

# 300秒 = 5分
if [ $TIME_DIFF -lt 300 ]; then
    exit 0
else
    exit 1
fi