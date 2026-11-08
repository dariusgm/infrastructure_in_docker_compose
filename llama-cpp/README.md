# llama.cpp services

Two `llama-server` instances built from llama.cpp (pinned to tag `b12205`) with the Vulkan backend.
They run natively on the host for now.

| Service | Model | Purpose |
| --- | --- | --- |
| Embeddings | `gpustack/bge-m3-GGUF:Q8_0` | Embeddings, CPU only (`--device none`), as on the workstation |
| OCR | `unsloth/Qwen3-VL-8B-Instruct-GGUF:Q4_K_M` | OCR for documents Tesseract cannot read |

## Host prerequisites

Ubuntu 24.04:

```bash
sudo apt update
sudo apt install -y libvulkan1 libvulkan-dev mesa-vulkan-drivers vulkan-tools glslc
sudo apt install -y cmake ninja-build build-essential libcurl4-openssl-dev spirv-headers
sudo usermod -aG render,video "$USER"   # log out and back in afterwards
```

Check that the Radeon iGPU is visible:

```bash
vulkaninfo --summary | grep -E 'deviceName|driverName'
```

Expected: `AMD Radeon Graphics (RADV RENOIR)` with `driverName = radv`. The `llvmpipe` software device
also listed is normal.

If the RADV line is missing, your shell does not have the `render` and `video` groups yet. Log out and
back in, or start the server from a new login session.

## Build llama-server

```bash
git clone --depth 1 --branch b12205 https://github.com/ggml-org/llama.cpp.git ~/llama.cpp
cd ~/llama.cpp
cmake -S . -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON \
  -DGGML_BACKEND_DL=ON -DGGML_VULKAN=ON \
  -DGGML_NATIVE=OFF -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON \
  -DLLAMA_CURL=ON -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF
cmake --build build --target llama-server -j"$(nproc)"
./build/bin/llama-server --list-devices
```

`--list-devices` must show the Radeon. If it prints `(none)`, see the prerequisites above.

## Run

Embeddings, on CPU as on the workstation:

```bash
~/llama.cpp/build/bin/llama-server -hf gpustack/bge-m3-GGUF:Q8_0 --embeddings --device none \
  -c 8192 -b 8192 -ub 8192 -t 4 --host 0.0.0.0 --port "$BGE_PORT"
```

OCR, on the Radeon through Vulkan:

```bash
~/llama.cpp/build/bin/llama-server -hf unsloth/Qwen3-VL-8B-Instruct-GGUF:Q4_K_M \
  -c 16384 --image-min-tokens 1024 --host 0.0.0.0 --port "$LLAMA_OCR_PORT"
```

`--image-min-tokens 1024` is the minimum that the model's grounding needs (llama.cpp warns without it).

Measured on the host (Ryzen 7 5825U, Radeon iGPU, 16 GB free RAM):

| | CPU only | Vulkan (iGPU) |
| --- | --- | --- |
| Prompt processing | 26.8 tok/s | 36.6 tok/s |
| Generation | 6.8 tok/s | 8.6 tok/s |

Without an API key, both servers accept any request. Keep them on the LAN only, or set `--api-key` before
exposing them further.

Models are cached in `~/.cache/huggingface/hub`.

## Docker (untested draft)

`Dockerfile` builds the same llama-server with Vulkan in an image. It has not been built or run yet.
Known open points: the `ldd` copy step may copy system libraries that should stay in the base image,
and the `GGML_BACKEND_DL` settings in the Dockerfile must match the native build above. Rootless Docker
access to `/dev/dri` is also untested.
