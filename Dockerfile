FROM ghcr.io/nerfstudio-project/nerfstudio:main

RUN apt update && apt install -y python3-pip git

WORKDIR /opt

RUN git clone https://github.com/KevinXu02/splatfacto-w.git && \
    pip3 install -e splatfacto-w

RUN git clone --recursive https://github.com/cvg/Hierarchical-Localization && \
    pip3 install -e Hierarchical-Localization

RUN ns-install-cli
