# Buckeye primary-run continuation environment.
#
# Reproduces the originating host closely enough that the cross-host
# equivalence gate should pass: same Python minor, same pinned numeric stack,
# same aqua-sim engine commit. Single-threaded BLAS is pinned deliberately —
# the solver is elementwise NumPy, and letting BLAS pick a thread count can
# change reduction order and therefore the arithmetic.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONHASHSEED=0 \
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# The ENGINE, pinned to the exact commit that produced the frozen checkpoint.
ARG AQUA_SIM_COMMIT=0b452c9d5ccffd88ea8308322087b09807242b4b
RUN git clone https://github.com/AkhilDhruva/aqua-sim /opt/aqua-sim \
    && cd /opt/aqua-sim \
    && git checkout ${AQUA_SIM_COMMIT} \
    && pip install --no-cache-dir -e .

WORKDIR /work
COPY . /work
ENV PYTHONPATH=/work/code

CMD ["python3", "crosshost_equivalence.py"]
