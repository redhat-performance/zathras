# Container Usage
## Quickstart
`podman run -v $SSH_KEY_PATH:/ssh -v $SCENARIO_PATH:/configs quay.io/zathras/zathras --scenario /configs/scenario --ssh_key_file /ssh/privkey.key`

## Supported Configurations
| Cloud type | Supported |
|------------|-----------|
| Local Systems | :white_check_mark: |
| AWS | :white_check_mark:|
| Azure | :x: |
| GCP | :x: |
| IBM Cloud | :x: |

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
| Variable Name | Cloud Type | Purpose |
|---------------|------------|---------|
| `AWS_ACCESS_KEY_ID` | AWS | Credentials to create AWS systems |
| `AWS_SECRET_ACCESS_KEY` | AWS | Credentials to create AWS systems |
| `AWS_DEFAULT_REGION` | AWS | Region to create the AWS system(s) |
