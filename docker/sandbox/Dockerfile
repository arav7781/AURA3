# aura-sandbox: the locked-down container that runs copilot code and converts office documents.
# It is always started with no network, a read-only root filesystem, a /tmp tmpfs, all capabilities
# dropped, and CPU / memory / pid / file-size limits (see backend/aura/sandbox/runner.py).
FROM python:3.13-slim-bookworm

# LibreOffice (headless, no GUI) converts PPTX/DOCX to PDF; poppler renders PDF pages to PNG previews.
# Carlito/Caladea are metric-compatible with Calibri/Cambria, so converted decks keep their layout.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-impress-nogui libreoffice-writer-nogui \
        poppler-utils fontconfig \
        fonts-crosextra-carlito fonts-crosextra-caladea fonts-liberation fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

RUN pip install --no-cache-dir \
        numpy==2.3.4 pandas==2.3.3 matplotlib==3.10.7 scipy==1.16.3 \
        python-pptx==1.0.2 openpyxl==3.1.5 pillow==11.3.0

# Matplotlib builds its font cache on first import; do it now so runs start fast on a read-only image.
ENV MPLBACKEND=Agg MPLCONFIGDIR=/opt/aura/mpl
RUN mkdir -p /opt/aura/mpl && python -c "import matplotlib.pyplot as plt; plt.figure()" && chmod -R a+rX /opt/aura

COPY runner.py /opt/aura/runner.py
ENV PYTHONPATH=/opt/aura PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOME=/tmp

WORKDIR /work
CMD ["python", "/opt/aura/runner.py", "/work/main.py"]
