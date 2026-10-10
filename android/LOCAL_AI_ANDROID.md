# Local AI on Android (no cloud account)

This adds a standalone chat tab to the OMEGA-X Android dashboard. It talks directly to a local `llama.cpp` OpenAI-compatible server on the same phone. No provider API key, cloud host, or OMEGA backend is needed for this chat tab.

**Important limitation:** this is local model chat only. The existing Runs, Agents, Browser, metrics, and persistent workflow features still require the separate OMEGA API, PostgreSQL, and Redis. This guide has not been verified on every Android device; compiling a model server on a phone can take a long time and may fail if RAM/storage are limited.

## 1. Install Termux

Install Termux from its official project source: https://github.com/termux/termux-app. Keep at least 5 GB of free storage available for build files and the model, and connect to Wi-Fi. The Q4 model below is about 491 MB; the source build needs additional space.

## Quick setup (recommended)

The repository includes a setup script that installs build tools, builds `llama-server`, downloads the model, and starts it locally. Review the script first if you prefer not to execute code downloaded from your repository.

In Termux, run:

```bash
curl -fsSL https://raw.githubusercontent.com/chester65r/omega-x-ascension/main/android/setup-local-ai-termux.sh -o ~/setup-omega-local-ai.sh
bash ~/setup-omega-local-ai.sh
```

The setup needs at least 5 GB free storage and may take a while. It checks the phone's total RAM: devices with around 5 GB RAM or more use **Qwen3-1.7B Q4_K_M** (about 1.28 GB); lower-memory devices fall back to **Qwen2.5-0.5B Q4_K_M** (about 491 MB) to reduce out-of-memory risk. Both are local, downloadable model weights; the larger model is more capable but still smaller than hosted frontier models. Keep the Termux session open while chatting. The server binds only to `127.0.0.1:8080` and does not enable model shell tools.

To explicitly choose a model before running the script, use `OMEGA_LOCAL_AI_MODEL=qwen3-1.7b bash ~/setup-omega-local-ai.sh` or `OMEGA_LOCAL_AI_MODEL=qwen2.5-0.5b bash ~/setup-omega-local-ai.sh`. Choose the larger one only if the phone has enough RAM and storage.

The manual steps below are available if the script fails or you want to inspect each command.

## 2. Build llama.cpp inside Termux

Open Termux and run:

```bash
pkg update && pkg upgrade -y
pkg install git cmake clang make curl -y
git clone https://github.com/ggml-org/llama.cpp.git
cd llama.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_OPENMP=OFF
cmake --build build --config Release -j2 --target llama-server
```

Keep `-j2` to reduce memory pressure. If Android closes Termux or the build fails due to memory, stop rather than repeatedly rebuilding; the phone may not have enough resources for this route.

## 3. Download a small model

The script selects a stronger Qwen3 1.7B quantized model when memory allows, and keeps Qwen 2.5 0.5B as the fallback. The Qwen3 Q4_K_M file is about 1.28 GB; the Qwen 2.5 Q4_K_M file is about 491 MB. These local models are useful for on-device chat but are not a substitute for a larger hosted model for complex multi-step agent jobs.

```bash
cd ~
curl -L --fail --retry 3 -o Qwen_Qwen3-1.7B-Q4_K_M.gguf \
  https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/136153a4f0744c0fa07aa2807d15c4bc6dd28709/Qwen_Qwen3-1.7B-Q4_K_M.gguf
```

## 4. Start the local server

From the `llama.cpp` directory, run:

```bash
./build/bin/llama-server \
  -m ~/Qwen_Qwen3-1.7B-Q4_K_M.gguf \
  -c 2048 -t 2 \
  --host 127.0.0.1 --port 8080 \
  --cors-origins https://appassets.androidplatform.net \
  --no-webui
```

Leave this Termux session running. It must listen on `127.0.0.1`, not `0.0.0.0`; do not expose this local server to your Wi-Fi network or the public internet. The CORS origin is restricted to the Android app's WebView asset origin.

If the server says the model is loaded, open OMEGA-X ASCENSION and choose **Local AI**. Keep the server URL as `http://127.0.0.1:8080`, tap **Test connection**, then send a short message.

## Troubleshooting

- **Build fails / Android kills Termux:** this phone may not have enough free RAM for a native build. Stop here and use a computer or a hosted inference provider instead; do not expect the OMEGA backend to run inside the Android app.
- **Test connection fails:** confirm the server is still running and shows port 8080. Re-check the CORS option and that the URL in the app is `http://127.0.0.1:8080`.
- **Responses are slow or basic:** expected for small local models on a phone. Close other apps and keep context size small; use the 0.5B model if the larger model runs out of memory.
- **Server exits when switching apps:** set Termux battery usage to unrestricted in Android settings, then retry.
- **Local chat works but Runs does not:** this is expected without the separate OMEGA backend; Local AI chat does not enable workflow execution or agent tools.

Reference documentation:
- llama.cpp Android / Termux notes: https://github.com/ggml-org/llama.cpp/blob/master/docs/android.md
- llama.cpp server options and CORS: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- Model page: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF
