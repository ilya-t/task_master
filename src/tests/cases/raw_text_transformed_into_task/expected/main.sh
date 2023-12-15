mkdir -p ../expected
set -e
echo "# [ ] $(date '+%Y.%m.%d') " > ../expected/main.md
cat ./main.md >> ../expected/main.md

$task_master ./main.md
