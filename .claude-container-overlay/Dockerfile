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

# 2026-07-09: Playwright + headless Chromium for browser-driving the viz UI.
# `install --with-deps chromium` pulls the ~30 system libs Chromium needs
# (libglib2.0-0, libnss3, libgbm1, ... — none are present in the base image).
# Browsers live in a shared, world-readable path so the non-root runtime user
# can launch them; the ENV persists to runtime so the Playwright CLI finds them.
# Global npm install pins a concrete Playwright version into the image, so the
# test-time CLI matches the baked browser build.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN npm install -g playwright \
    && playwright install --with-deps chromium \
    && chmod -R a+rX /opt/ms-playwright \
    && rm -rf /var/lib/apt/lists/*

# 2026-07-09: Nix with flakes (Determinate Systems installer). Needs no sudo and
# --init none skips the systemd daemon that has no place in a container.
# build-users-group is cleared so builds run as the calling user (no nixbld
# group); sandbox is off because the container can't set up build-sandbox user
# namespaces unprivileged. Install once and never edit this block (editing
# invalidates the Docker layer cache); per-package additions belong in a
# flake.nix checked into the repo, not here.
RUN curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix \
        -o /tmp/nix-installer.sh \
    && sh /tmp/nix-installer.sh install linux \
        --init none \
        --no-confirm \
        --extra-conf "experimental-features = nix-command flakes" \
        --extra-conf "build-users-group =" \
        --extra-conf "sandbox = false" \
    && rm /tmp/nix-installer.sh
ENV PATH=/nix/var/nix/profiles/default/bin:$PATH

# The build runs as root but claude-container's runtime user is created at start
# with a host-mapped UID. Daemon-less Nix run by that user fails trying to chmod
# root-owned /nix/var/nix/profiles/per-user (Operation not permitted). We can't
# chown to a UID that doesn't exist at build time, so make the store writable by
# any UID and delete the per-user dirs; the runtime user recreates+owns them on
# first `nix` call.
#
# CRITICAL: Determinate 3.x sets /nix/var/nix/profiles/default ->
# per-user/root/profile, i.e. the `nix` binary on PATH is reached *through*
# per-user. Deleting per-user before repointing default therefore nukes the nix
# CLI (dangling PATH, "nix: command not found"). So resolve the nix package in
# the store and repoint `default` straight at it FIRST — after that, default no
# longer routes through per-user and the cleanup is safe.
RUN nixpkg="$(dirname "$(dirname "$(readlink -f /nix/var/nix/profiles/default/bin/nix)")")" \
    && chmod -R go+rwX /nix \
    && ln -sfn "$nixpkg" /nix/var/nix/profiles/default \
    && rm -rf /nix/var/nix/profiles/per-user /nix/var/nix/gcroots/per-user \
    && test -x /nix/var/nix/profiles/default/bin/nix  # fail the build if PATH is broken
