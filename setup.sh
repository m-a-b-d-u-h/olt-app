#!/bin/bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
echo "Setup selesai. Jalankan: source venv/bin/activate && python app.py"
