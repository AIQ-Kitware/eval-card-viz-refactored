FROM kitware/trame:uv

# Set Python and Vue versions
ENV TRAME_PYTHON=3.11
ENV TRAME_CLIENT_TYPE=vue3
ENV UV_COMPILE_BYTECODE=0

# -------------------------------------------------------------------
# !!! Using path from root directory !!!
# -------------------------------------------------------------------
# Copy the local app and the deploy directory when using local
# directory (./setup/initialized.sh) instead of
# a published package (./setup/requirements.txt)
# => use one or the other
COPY --chown=trame-user:trame-user . /deploy
# -------------------------------------------------------------------

RUN /opt/trame/entrypoint.sh build