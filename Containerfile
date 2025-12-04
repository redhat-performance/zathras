FROM registry.fedoraproject.org/fedora:43

RUN dnf config-manager addrepo --from-repofile=https://rpm.releases.hashicorp.com/fedora/hashicorp.repo && \
    dnf install -y ssh-agent terraform python3-pip ansible-core hostname gh jq bc && pip3 install awscli
# SSH directory management since it'll be needed later
RUN mkdir ~/.ssh && chmod 700 ~/.ssh

WORKDIR /zathras
COPY ./bin/ /zathras/bin
RUN sh -c 'yes | ./bin/install.sh'
COPY . /zathras

ENV PATH "/root/.local/bin:$PATH"
