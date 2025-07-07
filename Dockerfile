FROM ghcr.io/nerfstudio-project/nerfstudio:main

RUN apt update && apt install -y python3-pip && apt install -y git
RUN pip3 install git+https://github.com/KevinXu02/splatfacto-w

RUN git clone --recursive https://github.com/cvg/Hierarchical-Localization/
RUN cd Hierarchical-Localization/ && pip3 install -e .
RUN ns-install-cli
