set -e
mkdir -p ./archive/custom.files > /dev/null
mv $1 ./archive/custom.files  > /dev/null
echo $1 | sed "s/main.files/custom.files/"