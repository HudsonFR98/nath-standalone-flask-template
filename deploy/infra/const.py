"""Constants shared by the infra helpers."""

# --- Environments -------------------------------------------------------------
# Every deployed environment gets its own VM, Pi-hole record, Terraform state
# (`<env>-vm`) and set of CI variables (`<ENV>_VM_FQDN`, `<ENV>_POSTGRES_*`, ...).
ENV_INTEGRATION = "integration"  # disposable: created, deployed, tested, destroyed by CI
ENV_VALIDATION = "validation"  # pre-production, no automated tests
ENV_PROD = "prod"
ENVIRONMENTS: tuple[str, ...] = (ENV_INTEGRATION, ENV_VALIDATION, ENV_PROD)
DEFAULT_ENVIRONMENT = ENV_PROD
# Names accepted for ad-hoc runs (e.g. `sandbox` for a local dry run).
ENVIRONMENT_NAME_PATTERN = r"^[a-z][a-z0-9-]*$"

# --- Pi-hole v6 REST API -----------------------------------------------------
PIHOLE_DEFAULT_URL = "http://192.168.1.105"
PIHOLE_AUTH_PATH = "/api/auth"
PIHOLE_DNS_HOSTS_PATH = "/api/config/dns/hosts"
PIHOLE_SID_HEADER = "X-FTL-SID"
PIHOLE_CSRF_HEADER = "X-FTL-CSRF"
PIHOLE_HTTP_TIMEOUT_S = 15

# --- IP allocation ------------------------------------------------------------
IP_POOL_DEFAULT_START = "192.168.1.124"
IP_POOL_DEFAULT_END = "192.168.1.200"
# Addresses inside the pool that must never be handed out even when no Pi-hole
# record exists for them (manually managed hosts).
IP_POOL_DEFAULT_RESERVED: tuple[str, ...] = ()
PING_TIMEOUT_S = 1

# --- Terraform ----------------------------------------------------------------
TERRAFORM_VM_RESOURCE_ADDRESS = "proxmox_virtual_environment_vm.app"
TERRAFORM_GENERATION_RESOURCE_ADDRESS = "terraform_data.generation"
TERRAFORM_ACTION_DELETE = "delete"
TERRAFORM_ACTION_CREATE = "create"
TERRAFORM_REPLACE_ACTIONS = ({"delete", "create"}, {"create", "delete"})
GENERATION_DEFAULT_SEED = 1

# --- SSH readiness --------------------------------------------------------------
SSH_PORT = 22
SSH_WAIT_DEFAULT_TIMEOUT_S = 300
SSH_WAIT_DEFAULT_INTERVAL_S = 5
SSH_DEFAULT_USER = "Nath"
# `cloud-init status --wait`: 0 = done, 2 = done with recoverable errors.
CLOUD_INIT_DONE_EXIT_CODES = (0, 2)

# --- dotenv artifact keys ----------------------------------------------------------
# Prefixed with the upper-cased environment name by `Environment.dotenv_key`,
# e.g. PROD_VM_IP / INTEGRATION_VM_IP, so several environments can coexist in
# one pipeline without clobbering each other's variables.
DOTENV_SUFFIX_VM_IP = "VM_IP"
DOTENV_SUFFIX_FQDN = "VM_FQDN"
DOTENV_SUFFIX_IP_REUSED = "VM_IP_REUSED"
DOTENV_SUFFIX_GENERATION = "VM_GENERATION"
