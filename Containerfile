FROM registry.fedoraproject.org/fedora:43

RUN dnf config-manager addrepo --from-repofile=https://rpm.releases.hashicorp.com/fedora/hashicorp.repo && \
    dnf install -y ssh-agent terraform python3-pip ansible-core hostname gh jq bc && pip3 install awscli
RUN pip3 install azure-cli
RUN curl -fsSL https://clis.cloud.ibm.com/install/linux | sh && \
    ibmcloud plugin install vpc-infrastructure -f && \
    ibmcloud plugin install cloud-object-storage -f
# SSH directory management since it'll be needed later
RUN mkdir ~/.ssh && chmod 700 ~/.ssh

WORKDIR /zathras
COPY ./bin/ /zathras/bin
RUN sh -c 'yes | ./bin/install.sh'
RUN dnf clean all && rm -rf /var/cache/dnf/

COPY . /zathras

ENV PATH="/root/.local/bin:$PATH"
ENV AWS_DEFAULT_OUTPUT="json"

ENTRYPOINT ["./burden"]
