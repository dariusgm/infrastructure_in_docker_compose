#!/usr/bin/env bash
# Start one llama-server natively on this host. See llama-cpp/README.md for the build.
#
#   llama-cpp/serve.sh embeddings   bge-m3 embeddings, CPU only (port BGE_PORT, default 8090)
#   llama-cpp/serve.sh ocr          Qwen3-VL-8B OCR on the Radeon iGPU via Vulkan (port LLAMA_OCR_PORT, default 8091)
#
# Extra arguments are passed to llama-server, e.g. llama-cpp/serve.sh ocr --api-key "$KEY".
# The binary is LLAMA_BIN (default ~/llama.cpp/build/bin/llama-server). Models are downloaded on the
# first start into ~/.cache/huggingface.
set -euo pipefail

role="${1:-}"
[ $# -gt 0 ] && shift

llama_bin="${LLAMA_BIN:-$HOME/llama.cpp/build/bin/llama-server}"

case "$role" in
  embeddings)
    port="${BGE_PORT:-8090}"
    args=(-hf gpustack/bge-m3-GGUF:Q8_0 --embeddings --device none
          -c 8192 -b 8192 -ub 8192 -t 4)
    ;;
  ocr)
    port="${LLAMA_OCR_PORT:-8091}"
    args=(-hf unsloth/Qwen3-VL-8B-Instruct-GGUF:Q4_K_M
          -c 16384 --image-min-tokens 1024)
    # The Vulkan device is only visible to users in the render group (see llama-cpp/README.md).
    if ! id -nG | tr ' ' '\n' | grep -qx render; then
      echo "warning: current shell is not in the 'render' group, the GPU will not be used." >&2
      echo "         Log out and back in, or check with: llama-server --list-devices" >&2
    fi
    ;;
  *)
    echo "usage: $0 embeddings|ocr [llama-server arguments...]" >&2
    exit 2
    ;;
esac

if [ ! -x "$llama_bin" ]; then
  echo "llama-server not found at $llama_bin, build it first (llama-cpp/README.md)." >&2
  exit 1
fi

exec "$llama_bin" "${args[@]}" --host 0.0.0.0 --port "$port" "$@"
