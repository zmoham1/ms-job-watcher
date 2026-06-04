@echo off
cd /d "C:\Users\Asus\OneDrive\Documents\New project\ms-job-watcher"
python watcher.py --mode boards --boards-batch-size 200 --hours-fresh 24 --always-send-summary
