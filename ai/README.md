# ai: language and embedding models for paperless

Paperless uses two local models for its AI features (suggestions, the LLM index and search). Both run
on the CPU in this stack, with no GPU. They use the OpenAI-compatible API of llama.cpp.

| Service | Model | Port on `HOST_IP` | Role |
| --- | --- | --- | --- |
| `llm` | Qwen3-VL-8B-Instruct, Q4_K_M, with its vision projector (`mmproj`) | 8091 | Chat model (`llm_endpoint`, model `qwen3-vl-8b`) |
| `embedding` | bge-m3, Q8_0 | 8090 | Embedding model (`llm_embedding_endpoint`, model `bge-m3`) |

Both services are built from llama.cpp at the commit `a691b2345844ce1b430201fc5fd404ce062e05f2`
(`.devops/cpu.Dockerfile`, target `server`). That is the same source the earlier native servers ran
from. Upgrading means changing the commit in `compose.yaml` (both services), reading the llama.cpp
release notes, and rebuilding.

## Data

The model files are not in git. They sit in `${DATA_DIR}/ai/models` and are mounted read-only:

- `Qwen3-VL-8B-Instruct-Q4_K_M.gguf` (about 5 GB)
- `mmproj-Qwen3-VL-8B-BF16.gguf` (about 1.2 GB)
- `bge-m3-Q8_0.gguf` (about 0.6 GB)

Losing them stops the services, but no data is lost. Keep a copy of the files, since the place they
came from is not recorded here.

## Settings

Set in `.env` (see `.env.example`). The paperless settings are read from the environment as
well, so the setup does not depend on the paperless database:

- `PAPERLESS_AI_*`: the paperless AI settings (`ENABLED`, `LLM_ENDPOINT`, `LLM_MODEL`, `LLM_CONTEXT_SIZE`,
  `LLM_REQUEST_TIMEOUT`, `LLM_EMBEDDING_ENDPOINT`, `LLM_EMBEDDING_MODEL`, and the backends). These are
  the fallbacks behind the values in the paperless database. The values in `.env` match the
  database, and any change to them must be made in both places.
- `LLM_MEMORY` (default `14g`), `LLM_CPUS` (default `8`), `EMBEDDING_MEMORY` (default `3g`),
  `EMBEDDING_CPUS` (default `4`).

Fixed in `compose.yaml`:

- **Context and vision.** `-c 16384` for the chat model, matching `llm_context_size`. The vision
  projector is loaded with the chat model.
- **Embeddings.** `--embeddings` with batch and ubatch 8192, for the bge-m3 model.
- **Ports on HOST_IP.** Paperless addresses the services by `HOST_IP`, so the published addresses
  must not change.

## Limits

- **No GPU.** The integrated AMD GPU hung under Vulkan (kernel compute-ring timeouts, Nov 10). Rootless
  Docker cannot pass the GPU into a container. The services are CPU-only.
- **Vision is not used by paperless.** Paperless 3.4 sends text only to the chat model. The projector
  is loaded so the server can accept images, but paperless sends none. Its remote OCR option supports
  only Azure AI, not a local model, so the document OCR stays Tesseract.
- **No API key.** Port 8091 and 8090 are open on the LAN, as before. Anyone on the LAN can call them.
  Paperless would need a key set in its settings if one is added to the servers.

## Checks

```bash
HOST=$(grep '^HOST_IP=' .env | cut -d= -f2-)
curl -s http://$HOST:8091/health      # {"status":"ok"} when the model is loaded
curl -s http://$HOST:8090/health
curl -s http://$HOST:8091/v1/chat/completions -H 'content-type: application/json' \
  --data '{"model":"qwen3-vl-8b","messages":[{"role":"user","content":"Reply with OK."}],"max_tokens":8}'
curl -s http://$HOST:8090/v1/embeddings -H 'content-type: application/json' \
  --data '{"model":"bge-m3","input":"test"}' | head -c 200
```

Paperless's own view of the settings: `GET /api/config/` (token required). The `llm_endpoint` and
`llm_embedding_endpoint` values there should equal the `.env` values.
