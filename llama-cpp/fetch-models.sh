#!/usr/bin/env bash
# Download the GGUF model files for serve.sh. Nothing is started. Run once, and again after a model change.
#
#   llama-cpp/fetch-models.sh            all models (about 7 GB)
#   llama-cpp/fetch-models.sh ocr        only the OCR model (about 6 GB)
#   llama-cpp/fetch-models.sh embeddings only the embedding model (about 0.6 GB)
#
# Files go to LLAMA_MODEL_DIR (default ~/llama-models). Files that are already complete are skipped.
set -euo pipefail

model_dir="${LLAMA_MODEL_DIR:-$HOME/llama-models}"
which_models="${1:-all}"

# repo, file in repo, local name
fetch_one() {
  local repo="$1" file="$2" dest="$model_dir/$3"
  local url="https://huggingface.co/$repo/resolve/main/$file"
  # Content-Length of the final redirect target, to detect complete files.
  local remote_size
  remote_size=$(curl -sIL "$url" | tr -d '\r' | awk 'tolower($1)=="content-length:" {size=$2} END {print size}')
  if [ -f "$dest" ] && [ "$(stat -c %s "$dest")" = "$remote_size" ]; then
    echo "ok: $dest"
    return
  fi
  echo "downloading $file -> $dest"
  curl -fL --retry 5 --retry-delay 10 -C - -o "$dest" "$url"
  if [ "$(head -c 4 "$dest")" != "GGUF" ]; then
    echo "error: $dest is not a GGUF file" >&2
    rm -f "$dest"
    exit 1
  fi
}

mkdir -p "$model_dir"

case "$which_models" in
  all|embeddings|ocr) ;;
  *) echo "usage: $0 [all|embeddings|ocr]" >&2; exit 2 ;;
esac

if [ "$which_models" = all ] || [ "$which_models" = embeddings ]; then
  fetch_one gpustack/bge-m3-GGUF bge-m3-Q8_0.gguf bge-m3-Q8_0.gguf
fi
if [ "$which_models" = all ] || [ "$which_models" = ocr ]; then
  fetch_one unsloth/Qwen3-VL-8B-Instruct-GGUF Qwen3-VL-8B-Instruct-Q4_K_M.gguf Qwen3-VL-8B-Instruct-Q4_K_M.gguf
  fetch_one unsloth/Qwen3-VL-8B-Instruct-GGUF mmproj-BF16.gguf mmproj-Qwen3-VL-8B-BF16.gguf
fi

echo "done: $model_dir"
