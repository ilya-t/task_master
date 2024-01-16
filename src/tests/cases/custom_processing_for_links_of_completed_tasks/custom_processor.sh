set -e
mkdir -p ./archive/custom.files > /dev/null

if [[ "$1" == *"files/error"* ]]; then
  echo "Error file detected!"
  exit 1
fi
mv $1 ./archive/custom.files  > /dev/null
echo "./custom.files/some.log"