#!/bin/bash
# Run once:  bash ~/Projects/clip-machine/setup-cloud.sh
set -e
cd ~/Projects/clip-machine
echo "1/3 Creating your PRIVATE GitHub repo and uploading the clip tools..."
U=$(gh api user -q .login)
if gh repo view "$U/clip-machine" >/dev/null 2>&1; then git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$U/clip-machine.git"; git push -q -u origin main; else gh repo create clip-machine --private --source . --push >/dev/null; fi
echo "2/3 Saving your keys into the repo's locked Secrets (never shown)..."
gh secret set PH_AUTOMATION_KEY --repo "$(gh api user -q .login)/clip-machine" < ~/.posthub_key
gh secret set GEMINI_API_KEY --repo "$(gh api user -q .login)/clip-machine" < ~/.gemini_key
echo "3/3 Starting the first test run..."
sleep 3; gh workflow run daily.yml --repo "$(gh api user -q .login)/clip-machine"
echo "DONE — private repo: https://github.com/$(gh api user -q .login)/clip-machine (tell Claude)"
