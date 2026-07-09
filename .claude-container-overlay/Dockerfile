# Scientific Python stack for the skelgraph package (point-cloud -> graph).
# Installed as system packages so they survive container restarts without the
# pip / PEP-668 bootstrap dance.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3-numpy \
        python3-scipy \
        python3-networkx \
        python3-pytest \
    && rm -rf /var/lib/apt/lists/*
