#!/bin/bash
cd "$(dirname "$0")"
echo "Installing dependencies..."
pip3 install -r requirements.txt
echo "Starting Tab Video Capture Backend..."
python3 main.py
