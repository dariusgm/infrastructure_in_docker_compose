# llama.cpp llama-server with the Vulkan backend. Used by llama-embeddings (bge-m3) and llama-ocr
# (Qwen3-VL). See llama-cpp/README.md.
#
# Pinned to a release tag: upgrade by changing LLAMA_CPP_TAG, reading the release notes first.
ARG LLAMA_CPP_TAG=b12205

FROM ubuntu:24.04 AS build

ARG LLAMA_CPP_TAG
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates git cmake build-essential ninja-build \
      libvulkan-dev glslc libcurl4-openssl-dev \
 && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${LLAMA_CPP_TAG}" https://github.com/ggml-org/llama.cpp.git /src/llama.cpp

WORKDIR /src/llama.cpp
# GGML_NATIVE=OFF: the binary must not depend on the CPU of the build machine. AVX2 and FMA
# cover every Ryzen and most Intel CPUs of the last ten years. Vulkan is the GPU backend.
RUN cmake -S . -B build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DGGML_VULKAN=ON \
      -DGGML_NATIVE=OFF \
      -DGGML_AVX2=ON \
      -DGGML_FMA=ON \
      -DGGML_F16C=ON \
      -DLLAMA_CURL=ON \
      -DLLAMA_BUILD_TESTS=OFF \
      -DLLAMA_BUILD_EXAMPLES=OFF \
 && cmake --build build --target llama-server -j"$(nproc)" \
 && mkdir -p /opt/llama/bin /opt/llama/lib \
 && cp build/bin/llama-server /opt/llama/bin/ \
 && find build -name '*.so*' -exec cp -P {} /opt/llama/lib/ \; \
 && ldd /opt/llama/bin/llama-server | awk '/=> \//{print $3}' | sort -u | xargs -I{} cp -L {} /opt/llama/lib/ \
 && ls /opt/llama/lib

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# mesa-vulkan-drivers provides the RADV driver for the Radeon iGPU. It also ships lavapipe (a
# software Vulkan device), which VK_ICD_FILENAMES below keeps out of the loader on purpose.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libvulkan1 mesa-vulkan-drivers libgomp1 libcurl4t64 ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --create-home --shell /usr/sbin/nologin llama

COPY --from=build /opt/llama /opt/llama

ENV LD_LIBRARY_PATH=/opt/llama/lib \
    VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.x86_64.json

USER 10001:10001
WORKDIR /home/llama
ENTRYPOINT ["/opt/llama/bin/llama-server"]
