set -e
./venv/bin/pytest --html=./tests/report.html --self-contained-html ./test.py
