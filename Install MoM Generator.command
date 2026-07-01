#!/bin/bash
# Double-click this ONCE to install everything MoM Generator needs.
# It does all the work for you — just wait for it to finish.

cd "$(dirname "$0")" || exit 1
clear
echo "════════════════════════════════════════════════════════"
echo "  📝  Installing MoM Generator"
echo "════════════════════════════════════════════════════════"
echo
echo "  This sets up everything on your Mac (one time)."
echo "  • It takes about 10–15 minutes and downloads a few GB."
echo "  • You may be asked for your Mac password once (that's normal)."
echo "  • Just leave this window open and wait."
echo
echo "  Starting…"
echo

bash ./setup.sh
STATUS=$?

echo
if [ "$STATUS" -eq 0 ]; then
  echo "════════════════════════════════════════════════════════"
  echo "  ✅  All set!"
  echo "  Now double-click  «Start MoM Generator.command»  to use it."
  echo "════════════════════════════════════════════════════════"
else
  echo "⚠️  Something didn't finish. Scroll up to see the message,"
  echo "    or send a screenshot to whoever shared this with you."
fi
echo
echo "You can close this window now (press any key)."
read -r -n 1
