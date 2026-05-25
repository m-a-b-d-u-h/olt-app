#!/bin/bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

if ! command -v pm2 &> /dev/null; then
    npm install -g pm2
fi

if pm2 describe olt-app &> /dev/null; then
    pm2 restart olt-app --update-env
else
    pm2 start ecosystem.config.js
fi
pm2 save
echo "Setup selesai. Aplikasi berjalan di http://localhost:3000"
