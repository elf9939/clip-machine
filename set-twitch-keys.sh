#!/bin/bash
# Saves YOUR Twitch developer app keys for the clip machine (Mac + cloud). Nothing is printed.
read -r -p "Twitch Client ID: " CID
read -r -s -p "Twitch Client Secret (hidden): " SEC; echo
CID=$(printf %s "$CID" | tr -d "[:space:]"); SEC=$(printf %s "$SEC" | tr -d "[:space:]")
# Mac Terminal sometimes pastes the secret more than once: keep one copy
if [ ${#SEC} -gt 30 ] && [ "${SEC:0:30}" = "${SEC:30:30}" ]; then SEC=${SEC:0:30}; fi
umask 077; printf '%s\n%s\n' "$CID" "$SEC" > ~/.twitch_keys
gh secret set TWITCH_CLIENT_ID --repo elf9939/clip-machine --body "$CID" && gh secret set TWITCH_CLIENT_SECRET --repo elf9939/clip-machine --body "$SEC" && echo "Saved ✓ (Mac + cloud)"
