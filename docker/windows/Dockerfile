FROM cdrx/pyinstaller-windows:python3

WORKDIR /src

# Install runtime and build dependencies into the Windows Python environment.
COPY requirements.txt /tmp/requirements.txt
RUN /entrypoint-windows.sh python -m pip install --upgrade pip setuptools wheel \
    && /entrypoint-windows.sh python -m pip install --no-cache-dir -r /tmp/requirements.txt \
    && /entrypoint-windows.sh python -m pip install --no-cache-dir pyinstaller
