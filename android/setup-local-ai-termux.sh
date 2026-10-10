#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# OMEGA-X ASCENSION — local llama.cpp setup for Termux.
# Downloads official llama.cpp source and a small public Qwen GGUF model.
APP_HOME="${OMEGA_LOCAL_AI_HOME:-$HOME/omega-local-ai}"
LLAMA_DIR="$APP_HOME/llama.cpp"
MODEL_NAME="qwen2.5-0.5b-instruct-q4_k_m.gguf"
MODEL_PATH="$APP_HOME/$MODEL_NAME"
MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/$MODEL_NAME"
CORS_ORIGIN="https://appassets.androidplatform.net"
MIN_FREE_KB=$((5 * 1024 * 1024))

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
note() { printf '\n[OMEGA Local AI] %s\n' "$*"; }

[[ -n "${PREFIX:-}" && -x "${PREFIX}/bin/pkg" ]] || fail "Run this script inside the Termux app, not a different shell."
case "$(uname -m)" in
  aarch64|arm64) ;;
  *) note "CPU architecture is $(uname -m). Building may be unsupported or unusually slow on this device." ;;
esac

command -v df >/dev/null 2>&1 || fail "The df command is unavailable."
free_kb="$(df -Pk "$HOME" | awk 'NR==2 {print $4}')"
[[ "${free_kb:-0}" =~ ^[0-9]+$ ]] || fail "Could not determine free storage."
(( free_kb >= MIN_FREE_KB )) || fail "At least 5 GB of free storage is recommended. Free space and run again."

note "Installing Termux build tools."
pkg update -y
pkg install -y git cmake clang make curl

mkdir -p "$APP_HOME"
if [[ ! -d "$LLAMA_DIR/.git" ]]; then
  note "Cloning the official llama.cpp repository."
  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$LLAMA_DIR"
fi

if [[ ! -x "$LLAMA_DIR/build/bin/llama-server" ]]; then
  note "Building llama-server using two jobs to limit memory use."
  cmake -S "$LLAMA_DIR" -B "$LLAMA_DIR/build" \
    -DCMAKE_BUILD_TYPE=Release -DGGML_OPENMP=OFF -DGGML_NATIVE=OFF
  cmake --build "$LLAMA_DIR/build" --config Release --parallel 2 --target llama-server
fi
[[ -x "$LLAMA_DIR/build/bin/llama-server" ]] || fail "llama-server was not produced by the build."

if [[ ! -f "$MODEL_PATH" ]] || [[ "$(stat -c '%s' "$MODEL_PATH" 2>/dev/null || echo 0)" -lt 400000000 ]]; then
  note "Downloading the Qwen 2.5 0.5B Q4_K_M model (about 491 MB)."
  curl --fail --location --retry 3 --retry-all-errors --continue-at - \
    --output "$MODEL_PATH" "$MODEL_URL"
fi
model_bytes="$(stat -c '%s' "$MODEL_PATH" 2>/dev/null || echo 0)"
(( model_bytes >= 400000000 )) || fail "The model download looks incomplete ($model_bytes bytes). Check free space/network and run again."

note "Starting the local model server on 127.0.0.1:8080."
note "Keep this Termux session open. In OMEGA-X ASCENSION, open Local AI and tap Test connection."
note "Only localhost is exposed; this script does not enable shell tools or public network access."
exec "$LLAMA_DIR/build/bin/llama-server" \
  --model "$MODEL_PATH" \
  --ctx-size 1024 \
  --threads 2 \
  --host 127.0.0.1 \
  --port 8080 \
  --cors-origins "$CORS_ORIGIN" \
  --no-webui
