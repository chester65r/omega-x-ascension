#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# OMEGA-X ASCENSION — local llama.cpp setup for Termux.
# Downloads official llama.cpp source and a small public Qwen GGUF model.
APP_HOME="${OMEGA_LOCAL_AI_HOME:-$HOME/omega-local-ai}"
LLAMA_DIR="$APP_HOME/llama.cpp"
MODEL_VARIANT="${OMEGA_LOCAL_AI_MODEL:-auto}"
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

device_ram_kb="$(awk '/^MemTotal:/ {print $2; exit}' /proc/meminfo)"
[[ "${device_ram_kb:-0}" =~ ^[0-9]+$ ]] || device_ram_kb=0
if [[ "$MODEL_VARIANT" == "auto" ]]; then
  if (( device_ram_kb >= 5000000 )); then
    MODEL_VARIANT="qwen3-1.7b"
  else
    MODEL_VARIANT="qwen2.5-0.5b"
  fi
fi

case "$MODEL_VARIANT" in
  qwen3-1.7b)
    MODEL_NAME="Qwen_Qwen3-1.7B-Q4_K_M.gguf"
    MODEL_URL="https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/136153a4f0744c0fa07aa2807d15c4bc6dd28709/Qwen_Qwen3-1.7B-Q4_K_M.gguf"
    MIN_MODEL_BYTES=1100000000
    MODEL_CTX_SIZE=2048
    ;;
  qwen2.5-0.5b)
    MODEL_NAME="qwen2.5-0.5b-instruct-q4_k_m.gguf"
    MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/$MODEL_NAME"
    MIN_MODEL_BYTES=400000000
    MODEL_CTX_SIZE=1024
    ;;
  *)
    fail "OMEGA_LOCAL_AI_MODEL must be auto, qwen3-1.7b, or qwen2.5-0.5b."
    ;;
esac
MODEL_PATH="$APP_HOME/$MODEL_NAME"
note "Selected $MODEL_VARIANT (device RAM: ${device_ram_kb} kB)."

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

model_bytes=0
if [[ -f "$MODEL_PATH" ]]; then
  model_bytes="$(wc -c < "$MODEL_PATH" | tr -d '[:space:]')"
fi
if (( model_bytes < MIN_MODEL_BYTES )); then
  if [[ "$MODEL_VARIANT" == "qwen3-1.7b" ]]; then
    note "Downloading the Qwen3 1.7B Q4_K_M model (about 1.28 GB)."
  else
    note "Downloading the Qwen 2.5 0.5B Q4_K_M model (about 491 MB)."
  fi
  if [[ -f "$MODEL_PATH" && "$model_bytes" -gt 0 ]]; then
    curl --fail --location --retry 3 --retry-all-errors --continue-at - \
      --output "$MODEL_PATH" "$MODEL_URL"
  else
    curl --fail --location --retry 3 --retry-all-errors \
      --output "$MODEL_PATH" "$MODEL_URL"
  fi
fi
model_bytes="$(wc -c < "$MODEL_PATH" | tr -d '[:space:]')"
(( model_bytes >= MIN_MODEL_BYTES )) || fail "The model download looks incomplete ($model_bytes bytes). Check free space/network and run again."

note "Starting $MODEL_VARIANT on 127.0.0.1:8080."
note "Keep this Termux session open. In OMEGA-X ASCENSION, open Local AI and tap Test connection."
note "Only localhost is exposed; this script does not enable shell tools or public network access."
exec "$LLAMA_DIR/build/bin/llama-server" \
  --model "$MODEL_PATH" \
  --ctx-size "$MODEL_CTX_SIZE" \
  --threads 2 \
  --host 127.0.0.1 \
  --port 8080 \
  --cors-origins "$CORS_ORIGIN" \
  --no-webui
