#!/bin/bash
# Saves YOUR Twitch developer app keys for the clip machine (Mac + cloud). Nothing is printed.
read -r -p "Twitch Client ID: " CID
read -r -s -p "Twitch Client Secret (hidden): " SEC; echo
umask 077; printf '%s\n%s\n' "$CID" "$SEC" > ~/.twitch_keys
gh secret set TWITCH_CLIENT_ID --repo elf9939/clip-machine --body "$CID" && gh secret set TWITCH_CLIENT_SECRET --repo elf9939/clip-machine --body "$SEC" && echo "Saved ✓ (Mac + cloud)"
