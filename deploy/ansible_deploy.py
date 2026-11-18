#!/usr/bin/env python3
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from infra import const  # noqa: E402

# action -> playbook. `deploy`/`update` converge the whole stack,
# `test` runs the Flask suite inside the already deployed app container.
PLAYBOOKS = {
    "deploy": "ansible/docker_deploy.yml",
    "update": "ansible/docker_deploy.yml",
    "test": "ansible/run_tests.yml",
}
ACTIONS_NEEDING_IMAGE = ("deploy", "update")

# Unpinned pip installs have pulled ansible-core 2.19.x, which can hit Galaxy
# KeyError: 'results' (galaxy cache / API). Cap below 2.19 until core is fixed.
ANSIBLE_CORE_SPEC = "ansible-core>=2.16.0,<2.19.0"


def ensure_ansible_installed():
    required_binaries = ["ansible-playbook", "ansible-galaxy"]
    missing_binaries = [binary for binary in required_binaries if shutil.which(binary) is None]
    if not missing_binaries:
        return

    print(
        "Ansible binaries missing (%s). Installing ansible-core with pip..."
        % ", ".join(missing_binaries),
        file=sys.stderr,
    )
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", ANSIBLE_CORE_SPEC])
    except subprocess.CalledProcessError as exc:
        print(f"Unable to install ansible-core: {exc}", file=sys.stderr)
        sys.exit(1)

    still_missing = [binary for binary in required_binaries if shutil.which(binary) is None]
    if still_missing:
        print(
            "Ansible installation completed but binaries are still missing: %s"
            % ", ".join(still_missing),
            file=sys.stderr,
        )
        sys.exit(1)


def install_ansible_collections():
    cmd = [
        "ansible-galaxy",
        "collection",
        "install",
        "-r",
        "ansible/requirements.yml",
        "--no-cache",
    ]
    last_error = None
    for attempt in range(1, 4):
        try:
            subprocess.check_call(cmd)
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if attempt < 3:
                print(
                    "ansible-galaxy failed (attempt %s/3), retrying..." % attempt,
                    file=sys.stderr,
                )
    print(f"Error installing Ansible collection: {last_error}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Deploy nath_standalone_flask_template using Ansible")
    parser.add_argument(
        "--action",
        choices=sorted(PLAYBOOKS),
        default="deploy",
        help="deploy/update: converge the stack; test: run pytest in the deployed app container",
    )
    parser.add_argument(
        "--env",
        choices=list(const.ENVIRONMENTS),
        required=True,
        help="Environment (inventory group and Flask context) to target",
    )
    parser.add_argument("--docker-image", help="Docker image to deploy (required for deploy/update)")
    parser.add_argument(
        "--test-labels",
        default="",
        help="Optional extra pytest arguments (action=test only)",
    )
    parser.add_argument(
        "--docker-registry",
        help="Image path prefix for third-party images (e.g. postgres, nginx) via GitLab Dependency Proxy",
    )
    parser.add_argument("--registry-username", help="Docker registry username")
    parser.add_argument("--registry-password", help="Docker registry password")
    parser.add_argument("--container-registry-server", help="Container registry server URL")
    parser.add_argument("--dependency-proxy-server", help="Dependency proxy server URL")
    parser.add_argument("--dependency-proxy-username", help="Dependency proxy username")
    parser.add_argument("--dependency-proxy-password", help="Dependency proxy password")
    parser.add_argument("--db-host", default="localhost", help="Database host")
    parser.add_argument(
        "--gitlab-ca-file",
        default=os.environ.get("GITLAB_CA_FILE"),
        help="Path on the Ansible controller to the GitLab CA certificate "
        "(defaults to $GITLAB_CA_FILE). Installed on the VM for Docker and the system trust store.",
    )
    parser.add_argument(
        "--ansible-user",
        default="Nath",
        help="SSH user Ansible connects as (cloud-init user of the VM template)",
    )
    parser.add_argument(
        "--become-password",
        default=os.environ.get("ANSIBLE_BECOME_PASSWORD"),
        help="sudo password for --ansible-user; only needed if passwordless sudo is not configured "
        "(defaults to $ANSIBLE_BECOME_PASSWORD)",
    )

    parser.add_argument("--postgres-user", help="PostgreSQL user")
    parser.add_argument("--postgres-password", help="PostgreSQL password")
    parser.add_argument("--postgres-db", help="PostgreSQL bootstrap database")
    parser.add_argument("--nsft-db-name", help="Application database name")
    parser.add_argument("--secret-key", help="Flask SECRET_KEY")
    parser.add_argument("--telegram-bot-token", help="Telegram bot token")
    parser.add_argument("--telegram-chat-id", help="Telegram chat ID")
    parser.add_argument("--admin-user-username", help="Initial admin username")
    parser.add_argument("--admin-user-password", help="Initial admin password")
    parser.add_argument("--admin-user-first-name", help="Initial admin first name")
    parser.add_argument("--admin-user-last-name", help="Initial admin last name")
    parser.add_argument("--admin-user-email", help="Initial admin email")
    parser.add_argument("--reviewer-user-username", help="Initial reviewer username")
    parser.add_argument("--reviewer-user-password", help="Initial reviewer password")
    parser.add_argument("--reviewer-user-first-name", help="Initial reviewer first name")
    parser.add_argument("--reviewer-user-last-name", help="Initial reviewer last name")
    parser.add_argument("--reviewer-user-email", help="Initial reviewer email")

    args = parser.parse_args()

    if args.action in ACTIONS_NEEDING_IMAGE and not args.docker_image:
        parser.error(f"--docker-image is required for --action {args.action}")

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    target_host = args.env
    playbook = PLAYBOOKS[args.action]

    ensure_ansible_installed()

    cmd = [
        "ansible-playbook",
        "-i",
        "ansible/inventory.ini",
        playbook,
        "-e",
        f"context={args.env}",
        "-e",
        f"target_host={target_host}",
        "-e",
        f"ansible_user={args.ansible_user}",
    ]

    if args.action == "test":
        if args.test_labels:
            cmd.extend(["-e", f"test_labels={args.test_labels}"])
    else:
        cmd.extend(["-e", f"deploy_action={args.action}"])
        cmd.extend(
            [
                "-e",
                f"docker_image={args.docker_image}",
                "-e",
                f"docker_registry={args.docker_registry or ''}",
                "-e",
                f"db_host={args.db_host}",
            ]
        )

    if args.gitlab_ca_file:
        cmd.extend(["-e", f"gitlab_ca_file={args.gitlab_ca_file}"])

    if args.become_password:
        cmd.extend(["-e", f"ansible_become_password={args.become_password}"])

    if args.registry_username:
        cmd.extend(["-e", f"registry_username={args.registry_username}"])
    if args.registry_password:
        cmd.extend(["-e", f"registry_password={args.registry_password}"])
    if args.container_registry_server:
        cmd.extend(["-e", f"container_registry_server={args.container_registry_server}"])
    if args.dependency_proxy_server:
        cmd.extend(["-e", f"dependency_proxy_server={args.dependency_proxy_server}"])
    if args.dependency_proxy_username:
        cmd.extend(["-e", f"dependency_proxy_username={args.dependency_proxy_username}"])
    if args.dependency_proxy_password:
        cmd.extend(["-e", f"dependency_proxy_password={args.dependency_proxy_password}"])

    context = args.env
    if args.postgres_user:
        cmd.extend(["-e", "postgres_user=%s" % args.postgres_user])
    if args.postgres_password:
        cmd.extend(["-e", f"{context}_postgres_password={args.postgres_password}"])
    if args.postgres_db:
        cmd.extend(["-e", "postgres_db=%s" % args.postgres_db])
    if args.nsft_db_name:
        cmd.extend(["-e", f"{context}_nsft_db_name={args.nsft_db_name}"])
    if args.secret_key:
        cmd.extend(["-e", f"{context}_secret_key={args.secret_key}"])
    if args.telegram_bot_token:
        cmd.extend(["-e", f"{context}_telegram_bot_token={args.telegram_bot_token}"])
    if args.telegram_chat_id:
        cmd.extend(["-e", f"{context}_telegram_chat_id={args.telegram_chat_id}"])
    if args.admin_user_username:
        cmd.extend(["-e", "admin_user_username=%s" % args.admin_user_username])
    if args.admin_user_password:
        cmd.extend(["-e", f"{context}_admin_user_password={args.admin_user_password}"])
    if args.admin_user_first_name:
        cmd.extend(["-e", "admin_user_first_name=%s" % args.admin_user_first_name])
    if args.admin_user_last_name:
        cmd.extend(["-e", "admin_user_last_name=%s" % args.admin_user_last_name])
    if args.admin_user_email:
        cmd.extend(["-e", "admin_user_email=%s" % args.admin_user_email])
    if args.reviewer_user_username:
        cmd.extend(["-e", "reviewer_user_username=%s" % args.reviewer_user_username])
    if args.reviewer_user_password:
        cmd.extend(["-e", f"{context}_reviewer_user_password={args.reviewer_user_password}"])
    if args.reviewer_user_first_name:
        cmd.extend(["-e", "reviewer_user_first_name=%s" % args.reviewer_user_first_name])
    if args.reviewer_user_last_name:
        cmd.extend(["-e", "reviewer_user_last_name=%s" % args.reviewer_user_last_name])
    if args.reviewer_user_email:
        cmd.extend(["-e", "reviewer_user_email=%s" % args.reviewer_user_email])

    try:
        install_ansible_collections()
    except FileNotFoundError:
        print("ansible-galaxy command not found after bootstrap.", file=sys.stderr)
        sys.exit(1)

    run_env = os.environ.copy()
    if args.action == "test":
        run_env["ANSIBLE_CALLBACK_RESULT_FORMAT"] = "yaml"
    try:
        subprocess.check_call(cmd, env=run_env)
    except FileNotFoundError:
        print("ansible-playbook command not found after bootstrap.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        print(f"Error running Ansible: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
