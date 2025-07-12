FROM ghcr.io/nerfstudio-project/nerfstudio:main

RUN apt update && apt upgrade -y && apt install -y python3-pip git && apt install -y wget

WORKDIR /opt

RUN git clone https://github.com/KevinXu02/splatfacto-w.git && \
    pip3 install -e splatfacto-w

RUN git clone --recursive https://github.com/cvg/Hierarchical-Localization && \
    pip3 install -e Hierarchical-Localization

RUN wget https://developer.download.nvidia.com/compute/cuda/11.8.0/local_installers/cuda_11.8.0_520.61.05_linux.run
RUN chmod +x cuda_11.8.0_520.61.05_linux.run && \
    ./cuda_11.8.0_520.61.05_linux.run --silent --toolkit

RUN git clone https://github.com/maturk/dn-splatter 
RUN cd dn-splatter/ && \
    pip install setuptools==69.5.1 && \
    pip install -e . && \
    pip install "numpy<2" && \
    ns-install-cli

RUN python dn-splatter/dn_splatter/data/download_scripts/download_omnidata.py
