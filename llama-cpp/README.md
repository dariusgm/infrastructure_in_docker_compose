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

## Install the models

Models are installed separately from the servers. Nothing is started:

```bash
llama-cpp/fetch-models.sh            # all models, about 7 GB
llama-cpp/fetch-models.sh ocr        # only the OCR model, about 6 GB
llama-cpp/fetch-models.sh embeddings # only bge-m3, about 0.6 GB
```

Files go to `$LLAMA_MODEL_DIR`, default `~/llama-models`. Complete files are skipped on a second run.

| File | Source |
| --- | --- |
| `bge-m3-Q8_0.gguf` | `gpustack/bge-m3-GGUF` |
| `Qwen3-VL-8B-Instruct-Q4_K_M.gguf` and `mmproj-Qwen3-VL-8B-BF16.gguf` | `unsloth/Qwen3-VL-8B-Instruct-GGUF` (`mmproj-BF16.gguf`) |

## Run

`serve.sh` starts one server from the installed files:

```bash
llama-cpp/serve.sh embeddings   # port $BGE_PORT, default 8090
llama-cpp/serve.sh ocr          # port $LLAMA_OCR_PORT, default 8091
```

Extra arguments go to `llama-server`, for example `llama-cpp/serve.sh ocr --api-key "$KEY"`. The
binary comes from `$LLAMA_BIN`, default `~/llama.cpp/build/bin/llama-server`. The `ocr` role warns if
the shell is not in the `render` group, because then the GPU is not used. If a model file is missing,
the script stops and names the `fetch-models.sh` command to run.

The commands the script runs are:

Embeddings, on CPU as on the workstation:

```bash
llama-server -m ~/llama-models/bge-m3-Q8_0.gguf --embeddings --device none \
  -c 8192 -b 8192 -ub 8192 -t 4 --host 0.0.0.0 --port "$BGE_PORT"
```

OCR, on the Radeon through Vulkan:

```bash
llama-server -m ~/llama-models/Qwen3-VL-8B-Instruct-Q4_K_M.gguf \
  --mmproj ~/llama-models/mmproj-Qwen3-VL-8B-BF16.gguf \
  -c 16384 --image-min-tokens 1024 --host 0.0.0.0 --port "$LLAMA_OCR_PORT"
```

`--image-min-tokens 1024` is the minimum that the model's grounding needs (llama.cpp warns without it).

The OCR server logs a warning that flash attention is disabled on Vulkan for layer 0. That is expected
for this model and build. It is a performance note, not an error. The iGPU's dedicated memory is nearly
full (about 3 of 3 GB) while the model runs, so a smaller `-c` or `--no-kv-offload` frees room if the
server gets slow or runs out of memory.

Measured on the host (Ryzen 7 5825U, Radeon iGPU, 16 GB free RAM):

| | CPU only | Vulkan (iGPU) |
| --- | --- | --- |
| Prompt processing | 26.8 tok/s | 36.6 tok/s |
| Generation | 6.8 tok/s | 8.6 tok/s |

Without an API key, both servers accept any request. Keep them on the LAN only, or set `--api-key` before
exposing them further.

Models are read from `$LLAMA_MODEL_DIR` (default `~/llama-models`), not from the Hugging Face cache.

## Docker (tested, CPU only)

`Dockerfile` builds llama-server with Vulkan in an image and matches the native build flags.

- The image builds. The embedding server runs on CPU and returns 1024-dimensional vectors.
- The Vulkan device is not reachable under rootless Docker. Inside the container, `/dev/dri/renderD128`
  appears as `nobody:nogroup`, and the container user cannot open it. Rootless Docker maps only the
  user's own UID and subordinate IDs, so the host's `render` group (GID 991) cannot be added with
  `--group-add`. `--device /dev/kfd` is not needed for Vulkan.
- Making the device world-readable would work, but it lets every local user open the GPU. Not done.
- Options: run the OCR server natively (works now, with the GPU), run the embedding server in the
  container (CPU, works), or switch this service to rootful Docker (changes the host setup).

Model cache: a named volume chowned to UID 10001 (`llama-hf-cache`, mounted at
`/home/llama/.cache/huggingface`). A bind mount owned by the host user is not writable from the
container.
