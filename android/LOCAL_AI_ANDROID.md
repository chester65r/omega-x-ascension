# Local AI on Android (no cloud account)

This adds a standalone chat tab to the OMEGA-X Android dashboard. It talks directly to a local `llama.cpp` OpenAI-compatible server on the same phone. No provider API key, cloud host, or OMEGA backend is needed for this chat tab.

**Important limitation:** this is local model chat only. The existing Runs, Agents, Browser, metrics, and persistent workflow features still require the separate OMEGA API, PostgreSQL, and Redis. This guide has not been verified on every Android device; compiling a model server on a phone can take a long time and may fail if RAM/storage are limited.

## 1. Install Termux

Install Termux from its official project source: https://github.com/termux/termux-app. Keep at least 3 GB of free storage available for build files and the model, and connect to Wi-Fi. The Q4 model below is about 491 MB; the source build needs additional space.

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

This Qwen 2.5 0.5B quantized model is a compact starting point, not a high-capability model. The model file is about 491 MB and is published under the Apache-2.0 license on Hugging Face.

```bash
cd ~
curl -L --fail --retry 3 -o qwen2.5-0.5b-instruct-q4_k_m.gguf \
  https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf
```

## 4. Start the local server

From the `llama.cpp` directory, run:

```bash
./build/bin/llama-server \
  -m ~/qwen2.5-0.5b-instruct-q4_k_m.gguf \
  -c 1024 -t 2 \
  --host 127.0.0.1 --port 8080 \
  --cors-origins https://appassets.androidplatform.net \
  --no-webui
```

Leave this Termux session running. It must listen on `127.0.0.1`, not `0.0.0.0`; do not expose this local server to your Wi-Fi network or the public internet. The CORS origin is restricted to the Android app's WebView asset origin.

If the server says the model is loaded, open OMEGA-X ASCENSION and choose **Local AI**. Keep the server URL as `http://127.0.0.1:8080`, tap **Test connection**, then send a short message.

## Troubleshooting

- **Build fails / Android kills Termux:** this phone may not have enough free RAM for a native build. Stop here and use a computer or a hosted inference provider instead; do not expect the OMEGA backend to run inside the Android app.
- **Test connection fails:** confirm the server is still running and shows port 8080. Re-check the CORS option and that the URL in the app is `http://127.0.0.1:8080`.
- **Responses are slow or basic:** expected for a 0.5B model on a phone. Close other apps and keep context size small.
- **Server exits when switching apps:** set Termux battery usage to unrestricted in Android settings, then retry.
- **Local chat works but Runs does not:** this is expected without the separate OMEGA backend; Local AI chat does not enable workflow execution or agent tools.

Reference documentation:
- llama.cpp Android / Termux notes: https://github.com/ggml-org/llama.cpp/blob/master/docs/android.md
- llama.cpp server options and CORS: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
- Model page: https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF
