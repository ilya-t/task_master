mkdir -p ../expected
set -e
DATE="$(date '+%Y.%m.%d')"
cat > ../expected/main.md <<EOF
# >>> (Active) <<<
- [${DATE}](main.md#L4)

# [-] ${DATE} 
EOF
cat ./main.md >> ../expected/main.md

$task_master ./main.md
