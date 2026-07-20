# Container Usage
## Quickstart
`podman run -v $SSH_KEY_PATH:/ssh -v $SCENARIO_PATH:/configs quay.io/zathras/zathras --scenario /configs/scenario --ssh_key_file /ssh/privkey.key`

## Supported Configurations
| Cloud type | Supported |
|------------|-----------|
| Local Systems | :white_check_mark: |
| AWS | :white_check_mark:|
| Azure | :construction: |
| GCP | :x: |
| IBM Cloud | :construction: |

:white_check_mark: - Full support, should be able to use the default entrypoint

:construction: - Works but requires manual command invocations, requiring 
changing the container entrypoint by using something like
`--entrypoint /bin/bash`.

:x: - No support, should work but needs package installation in order to function.

## Volumes

### SSH Keys
SSH keys should be placed in their own volume, and it can be mounted anywhere, so long as `--ssh_key_file` is set to a key in that path.
#### Sample Volme mount
`-v $SSH_PATH:/ssh ... --ssh_key_file /ssh/$PRIVKEY`

### Scenario Files
Scenario files can be placed in a volume, and can also be mounted anywhere, so long as `--scenario` is provided to a file at the mounted path.
#### Sample Volme mount
`-v $SCENARIO_PATH:/scenarios ... --scenario /scenarios/$FILE`

### Local Configs
Local configs should be placed in a volume, but it cannot be mounted anywhere, it must be mounted at `/zathras/local_configs`.
#### Sample Volme mount
`-v $CONFIG_PATH:/zathras/local_configs`

## Enviornment Variables
### AWS
| Variable Name | Purpose |
|---------------|---------|
| `AWS_ACCESS_KEY_ID` | Credentials to create AWS systems |
| `AWS_SECRET_ACCESS_KEY` | Credentials to create AWS systems |
| `AWS_DEFAULT_REGION` | Region to create the AWS system(s) |

### Azure
Requires `az login` to run.  Consult the [documentation](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli?view=azure-cli-latest)
on how to provide the needed information.

### IBMCloud
Requires `ibmcloud login` to function.  Consult the [documentation](https://cloud.ibm.com/docs/cli?topic=cli-ibmcloud_cli#ibmcloud_login)
on how to provide the needed information.

Once logged in, run `ibmcloud target -g <resource group name>` to set the resource group.

