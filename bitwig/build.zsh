#!/usr/bin/env zsh
set -euo pipefail

# Builds two .bwextension bundles from one Java codebase:
#   ROLI-Lightpad-Block-M.bwextension           — Enhanced Mixer (auto-detects Lightpad ports)
#   ROLI-Lightpad-Block-4faders.bwextension     — transport only (no auto-detect; add manually)

ROOT="${0:A:h}"
SRC_JAVA="$ROOT/src/main/java"
CLASSES="$ROOT/build/classes"
OUT_EXT="$ROOT/build"
STAGING_MIXER="$OUT_EXT/staging-mixer"
STAGING_4F="$OUT_EXT/staging-4faders"
BITWIG_APP_PATH="${BITWIG_APP_PATH:-/Applications/Bitwig Studio.app}"
BW_JAR="${BITWIG_JAR:-$BITWIG_APP_PATH/Contents/Java/bitwig.jar}"

if [[ ! -r $BW_JAR ]]; then
  print -u2 "Missing Bitwig API jar: $BW_JAR"
  print -u2 "Set BITWIG_APP_PATH or BITWIG_JAR before running build.zsh."
  exit 1
fi

rm -rf "$CLASSES" "$STAGING_MIXER" "$STAGING_4F"
mkdir -p "$CLASSES" "$STAGING_MIXER" "$STAGING_4F"
typeset -a java_sources
java_sources=( "$SRC_JAVA"/**/*.java(N) )
if (( ${#java_sources[@]} == 0 )); then
  print -u2 "No Java sources under $SRC_JAVA"
  exit 1
fi
javac \
  --release 8 \
  -encoding UTF-8 \
  -Xlint:-options \
  -d "$CLASSES" \
  -cp "$BW_JAR" \
  "${java_sources[@]}"

rsync -a --delete "$CLASSES/" "$STAGING_MIXER/"
rsync -a --delete "$CLASSES/" "$STAGING_4F/"

mkdir -p "$STAGING_MIXER/META-INF/services" "$STAGING_4F/META-INF/services"
print -r -- 'com.naenyn.lightpad.bitwig.LightpadBlockExtensionDefinition' \
  >"$STAGING_MIXER/META-INF/services/com.bitwig.extension.ExtensionDefinition"
print -r -- 'com.naenyn.lightpad.bitwig.LightpadBlock4fadersExtensionDefinition' \
  >"$STAGING_4F/META-INF/services/com.bitwig.extension.ExtensionDefinition"

BWEXT_MIXER="$OUT_EXT/ROLI-Lightpad-Block-M.bwextension"
BWEXT_4F="$OUT_EXT/ROLI-Lightpad-Block-4faders.bwextension"
rm -f "$BWEXT_MIXER" "$BWEXT_4F"
( cd "$STAGING_MIXER" && jar cf "$BWEXT_MIXER" . )
( cd "$STAGING_4F" && jar cf "$BWEXT_4F" . )

print "Built $BWEXT_MIXER"
print "Built $BWEXT_4F"
