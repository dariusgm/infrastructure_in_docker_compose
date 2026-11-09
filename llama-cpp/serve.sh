#!/usr/bin/env bash
# Start one llama-server natively on this host. See llama-cpp/README.md for the build.
#
#   llama-cpp/serve.sh embeddings   bge-m3 embeddings, CPU only (port BGE_PORT, default 8090)
#   llama-cpp/serve.sh ocr          Qwen3-VL-8B OCR on the Radeon iGPU via Vulkan (port LLAMA_OCR_PORT, default 8091)
#
# Extra arguments are passed to llama-server, e.g. llama-cpp/serve.sh ocr --api-key "$KEY".
# The binary is LLAMA_BIN (default ~/llama.cpp/build/bin/llama-server). The model files must be
# installed first with llama-cpp/fetch-models.sh; they are read from LLAMA_MODEL_DIR (default ~/llama-models).
set -euo pipefail

role="${1:-}"
[ $# -gt 0 ] && shift

llama_bin="${LLAMA_BIN:-$HOME/llama.cpp/build/bin/llama-server}"
model_dir="${LLAMA_MODEL_DIR:-$HOME/llama-models}"

case "$role" in
  embeddings)
    port="${BGE_PORT:-8090}"
    args=(-m "$model_dir/bge-m3-Q8_0.gguf" --embeddings --device none
          -c 8192 -b 8192 -ub 8192 -t 4)
    required=("$model_dir/bge-m3-Q8_0.gguf")
    ;;
  ocr)
    port="${LLAMA_OCR_PORT:-8091}"
    args=(-m "$model_dir/Qwen3-VL-8B-Instruct-Q4_K_M.gguf"
          --mmproj "$model_dir/mmproj-Qwen3-VL-8B-BF16.gguf"
          -c 16384 --image-min-tokens 1024)
    required=("$model_dir/Qwen3-VL-8B-Instruct-Q4_K_M.gguf" "$model_dir/mmproj-Qwen3-VL-8B-BF16.gguf")
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

for file in "${required[@]}"; do
  if [ ! -f "$file" ]; then
    echo "model file missing: $file" >&2
    echo "install it first: llama-cpp/fetch-models.sh $role" >&2
    exit 1
  fi
done

exec "$llama_bin" "${args[@]}" --host 0.0.0.0 --port "$port" "$@"
