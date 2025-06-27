set -e
cd src
rm -rf ./venv
python3 -m venv ./venv
source venv/bin/activate
pip3 install -r ./requirements.txt

# test requirements
pip3 install parameterized==0.9.0
pip3 install pytest-html==3.2.0
cd ..

# exec script generation
exec_script=./run
echo "#!$(pwd)/src/venv/bin/python3" > $exec_script
echo "# FILE IS GENERATED!" >> $exec_script
echo "import os" >> $exec_script
echo "import sys" >> $exec_script
echo "sys.path.append(os.path.dirname(__file__)+'/src')" >> $exec_script
echo "import main" >> $exec_script
echo "main.main()" >> $exec_script
chmod +x $exec_script

echo '================================='
echo 'Setup is completed. Run app with:'
echo '  ./run --help'
