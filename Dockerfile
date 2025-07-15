FROM ghcr.io/nerfstudio-project/nerfstudio:main

RUN apt update && apt upgrade -y && apt install -y python3-pip git && apt install -y wget

WORKDIR /opt

RUN git clone https://github.com/KevinXu02/splatfacto-w.git && \
    pip3 install -e splatfacto-w

RUN git clone --recursive https://github.com/cvg/Hierarchical-Localization && \
    pip3 install -e Hierarchical-Localization

RUN wget https://demuc.de/colmap/vocab_tree_flickr100K_words32K.bin -O /opt/vocab_tree_flickr100K_words32K.bin

RUN pip3 uninstall nerfstudio -y

RUN echo "downloading latest custom nerfstudio" && git clone https://github.com/Jourdelune/nerfstudio.git && \
    cd nerfstudio && \
    pip3 install --upgrade pip setuptools && \
    pip3 install .

RUN ns-install-cli --mode install
