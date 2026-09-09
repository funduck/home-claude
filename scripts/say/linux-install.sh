# This script helps to install alternative for "say" on Linux
pip install piper-tts

mkdir ~/.piper
cd ~/.piper

python3 -m piper.download_voices en_US-lessac-medium
python3 -m piper.download_voices ru_RU-irina-medium

# test
python3 -m piper -m en_US-lessac-medium --data-dir ~/.piper -- 'This will play on your speakers.'
sleep 1
python3 -m piper -m ru_RU-irina-medium --data-dir ~/.piper -- 'Это прозвучит в ваших динамиках.'
