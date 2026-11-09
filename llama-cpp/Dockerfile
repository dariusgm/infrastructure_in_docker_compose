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
      libvulkan-dev glslc spirv-headers libssl-dev \
 && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${LLAMA_CPP_TAG}" https://github.com/ggml-org/llama.cpp.git /src/llama.cpp

WORKDIR /src/llama.cpp
# Same flags as the native build in llama-cpp/README.md. GGML_BACKEND_DL=ON builds the backends
# (Vulkan, CPU) as shared libraries that llama-server loads from its own directory at start. With
# static backends the Vulkan device is never registered.
# GGML_NATIVE=OFF: the binary must not depend on the CPU of the build machine. AVX2 and FMA
# cover every Ryzen and most Intel CPUs of the last ten years.
RUN cmake -S . -B build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_SHARED_LIBS=ON \
      -DGGML_BACKEND_DL=ON \
      -DGGML_VULKAN=ON \
      -DGGML_NATIVE=OFF \
      -DGGML_AVX2=ON \
      -DGGML_FMA=ON \
      -DGGML_F16C=ON \
      -DLLAMA_BUILD_TESTS=OFF \
      -DLLAMA_BUILD_EXAMPLES=OFF \
 && cmake --build build --target llama-server -j"$(nproc)" \
 && mkdir -p /opt/llama/bin \
 && cp build/bin/llama-server /opt/llama/bin/ \
 && cp -P build/bin/*.so* /opt/llama/bin/ \
 && ls /opt/llama/bin

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# mesa-vulkan-drivers provides the RADV driver for the Radeon iGPU. It also ships lavapipe (a
# software Vulkan device), which VK_ICD_FILENAMES below keeps out of the loader on purpose.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libvulkan1 mesa-vulkan-drivers libgomp1 libssl3t64 ca-certificates curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --create-home --shell /usr/sbin/nologin llama

# The binary and its shared libraries live in one directory: llama-server finds the backends there.
COPY --from=build /opt/llama/bin /opt/llama/bin

ENV LD_LIBRARY_PATH=/opt/llama/bin \
    VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/radeon_icd.x86_64.json

USER 10001:10001
WORKDIR /home/llama
ENTRYPOINT ["/opt/llama/bin/llama-server"]
