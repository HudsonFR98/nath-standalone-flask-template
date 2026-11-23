# 03 — Pi-hole DNS record and IP allocation

## What we need from Pi-hole

1. Read the current local DNS records (`dns.hosts`).
2. If `nsft.nath-server.home` already has a record → return its IP (idempotent path).
3. Otherwise pick the first IP in `192.168.1.124`–`192.168.1.200` that is not already used, and create `<ip> nsft.nath-server.home`.
4. Optionally delete the record (manual `destroy_prod_vm` job).

`ASSUMPTION: Pi-hole v6` (FTL with the built-in REST API on port 80/443). Pi-hole v5 has a different PHP API (`/admin/api.php?customdns&action=add&ip=..&domain=..&auth=<token>`); the client below isolates that behind an interface so a v5 backend is a small extra class.

## Pi-hole v6 API in three calls

```bash
PIHOLE=http://192.168.1.105

# 1. Session (use an "application password" generated in Settings → Web interface/API, not the admin password)
curl -s -X POST "$PIHOLE/api/auth" -H 'Content-Type: application/json' \
     -d '{"password":"<APP_PASSWORD>"}'
# → {"session":{"valid":true,"sid":"...","csrf":"...","validity":300}}

# 2. List local records
curl -s "$PIHOLE/api/config/dns/hosts" -H "X-FTL-SID: $SID" -H "X-FTL-CSRF: $CSRF"
# → {"config":{"dns":{"hosts":["192.168.1.108 d13t.nath-server.home","192.168.1.114 anytype.nath-server.home", ...]}}}

# 3. Add a record (value is "<ip> <domain>", URL-encoded, no body)
curl -s -X PUT "$PIHOLE/api/config/dns/hosts/192.168.1.124%20nsft.nath-server.home" \
     -H "X-FTL-SID: $SID" -H "X-FTL-CSRF: $CSRF"

# Remove
curl -s -X DELETE "$PIHOLE/api/config/dns/hosts/192.168.1.124%20nsft.nath-server.home" \
     -H "X-FTL-SID: $SID" -H "X-FTL-CSRF: $CSRF"

# Log out (sessions are limited; be polite)
curl -s -X DELETE "$PIHOLE/api/auth" -H "X-FTL-SID: $SID"
```

Pi-hole applies `dns.hosts` changes immediately (FTL reloads its local records) — no restart needed.

Optional extra sources of "used" IPs, if Pi-hole is also your DHCP server: `GET /api/dhcp/leases`. If DHCP is on the router instead, the pool `.124–.200` must simply be outside the router's DHCP range (open question in 06).

## IP allocation algorithm

```text
allocate(fqdn, pool=[.124 .. .200]):
    records = pihole.list_hosts()                       # [(ip, domain), ...]
    existing = [ip for ip, domain in records if domain == fqdn]
    if fixed_ip:                                        # optional <ENV>_VM_IP
        if another name already owns fixed_ip: fail    # do not scan the pool
        point fqdn at fixed_ip (replace a different record for this fqdn)
        return fixed_ip

    if existing:
        return existing[0], reused=True                 # idempotent path

    used  = {ip for ip, _ in records}
    used |= {lease.ip for lease in pihole.list_dhcp_leases()}   # only if Pi-hole does DHCP
    used |= reserved_ips_from_ci_variable                      # e.g. "192.168.1.150,192.168.1.151"

    for ip in pool:
        if ip in used:            continue
        if probe and is_alive(ip): continue             # optional ARP/ICMP probe, see below
        pihole.put_host(ip, fqdn)
        return ip, reused=False

    raise NoFreeIpError(pool)
```

The Pi-hole record is the reservation: creating it is the last step of allocation and the first thing checked on the next run.

Worked example with today's records: `.108 d13t` and `.114 anytype` are both below the pool and irrelevant, so a first run picks `.124`. If a record inside the pool ever appears (say `.130 something`), it lands in `used` and the allocator steps over it.

### Liveness probe (optional, default on)

Pi-hole only knows what was declared. A device with a hard-coded IP in the pool would not appear. The allocator can run `ping -c1 -W1 <ip>` (ICMP) before choosing; the runner is on the same L2 segment so this is reliable enough. Cost: at most ~77 pings on a first run, none afterwards. Disable with `--no-probe` if the runner cannot ping the LAN.

### Pinning the IP against accidental Pi-hole edits

If someone deletes the record by hand while the VM lives, the next run would allocate a *different* IP and Terraform would try to re-IP the VM. To avoid that, `allocate_prod_ip` first asks Terraform state (cheap: `terraform output -raw vm_ip`, or the `PROD_VM_IP` value stored as a GitLab CI **project variable** written by the job through the API) and, if present, re-creates the record with **that** IP instead of allocating a new one.

Recommended order of truth:

1. Pi-hole record for the FQDN (normal case)
2. Terraform state output `vm_ip` (record lost)
3. Fresh allocation (first run)

## Python design (OOP, in `deploy/infra/`)

Same spirit as the existing `deploy/ansible_deploy.py`: standard library only (`urllib`, `ipaddress`, `json`, `subprocess`) so the CI image stays `python:3.11-slim` with nothing to install.

```python
# deploy/infra/pihole_client.py
@dataclass(frozen=True)
class DnsHostRecord:
    ip: ipaddress.IPv4Address
    domain: str

class PiholeClient:
    """Pi-hole v6 REST client. Context manager: logs in on enter, logs out on exit."""
    def __init__(self, base_url: str, app_password: str, timeout: int = 10) -> None: ...
    def __enter__(self) -> "PiholeClient": ...      # POST /api/auth → sid, csrf
    def __exit__(self, *exc) -> None: ...            # DELETE /api/auth
    def list_hosts(self) -> list[DnsHostRecord]: ... # GET /api/config/dns/hosts
    def put_host(self, record: DnsHostRecord) -> None: ...     # PUT  /api/config/dns/hosts/{value}
    def delete_host(self, record: DnsHostRecord) -> None: ...  # DELETE ...
    def list_dhcp_leases(self) -> list[ipaddress.IPv4Address]: ...  # GET /api/dhcp/leases (may be empty)

# deploy/infra/ip_allocator.py
@dataclass(frozen=True)
class IpPool:
    first: ipaddress.IPv4Address   # 192.168.1.124
    last: ipaddress.IPv4Address    # 192.168.1.200
    def __iter__(self): ...

class LivenessProbe(Protocol):
    def is_alive(self, ip: ipaddress.IPv4Address) -> bool: ...

class IcmpProbe: ...       # ping -c1 -W1
class NoProbe: ...         # always False

@dataclass(frozen=True)
class Allocation:
    ip: ipaddress.IPv4Address
    fqdn: str
    reused: bool

class IpAllocator:
    def __init__(self, client: PiholeClient, pool: IpPool, probe: LivenessProbe,
                 reserved: frozenset[ipaddress.IPv4Address] = frozenset(),
                 pinned_ip: ipaddress.IPv4Address | None = None) -> None: ...
    def allocate(self, fqdn: str) -> Allocation: ...
    def release(self, fqdn: str) -> None: ...
```

CLI (`deploy/infra_deploy.py`). The application password is read from the
`PIHOLE_APP_PASSWORD` environment variable, never from argv, so it cannot leak
into job logs:

```bash
export PIHOLE_APP_PASSWORD='<application password>'
python3 deploy/infra_deploy.py allocate-ip \
    --pihole-url http://192.168.1.105 \
    --fqdn nsft.nath-server.home --pool-start 192.168.1.124 --pool-end 192.168.1.200 \
    --env prod --fixed-ip "${PROD_VM_IP:-}" --output infra.env
# writes infra.env (keys prefixed by --env: INTEGRATION_VM_IP, VALIDATION_VM_IP, PROD_VM_IP):
#   PROD_VM_IP=192.168.1.124
#   PROD_VM_FQDN=nsft.nath-server.home
#   PROD_VM_IP_REUSED=false

python3 deploy/infra_deploy.py release-ip --fqdn nsft.nath-server.home ...   # used by destroy_<env>_vm
```

Errors are explicit and fail the job: auth failure, no free IP, record exists with two different IPs (ambiguous), FQDN present but IP outside pool (warn only — a hand-managed record is allowed).

## Unit-test strategy

`PiholeClient` is injected, so `IpAllocator` is testable with a fake client holding a list of records. Cases: reuse existing, skip used, skip alive, pool exhausted, pinned IP re-created. These tests live in a plain `unittest` module under `deploy/infra/tests` and are run on a developer machine, not in the integration VM pipeline.

## Constants

Pool bounds, Pi-hole URL, DNS domain and the record format belong in a small `deploy/infra/const.py` (same convention as `const.py` in the app), overridable by CLI flags / CI variables.
