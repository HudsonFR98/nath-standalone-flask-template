#!/usr/bin/env python3
import argparse
import subprocess
import os
import sys
import shutil


def ensure_ansible_installed():
    required_binaries = ['ansible-playbook', 'ansible-galaxy']
    missing_binaries = [binary for binary in required_binaries if shutil.which(binary) is None]
    if not missing_binaries:
        return

    print(
        "Ansible binaries missing (%s). Installing ansible-core with pip..."
        % ", ".join(missing_binaries),
        file=sys.stderr
    )
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'ansible-core'])
    except subprocess.CalledProcessError as exc:
        print(f"Unable to install ansible-core: {exc}", file=sys.stderr)
        sys.exit(1)

    still_missing = [binary for binary in required_binaries if shutil.which(binary) is None]
    if still_missing:
        print(
            "Ansible installation completed but binaries are still missing: %s"
            % ", ".join(still_missing),
            file=sys.stderr
        )
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Deploy nath_standalone_flask_template using Ansible')
    parser.add_argument('--action', choices=['deploy', 'update'], default='deploy', help='Action to perform')
    parser.add_argument('--env', choices=['test', 'demo', 'prod'], required=True, help='Environment to deploy to')
    parser.add_argument('--docker-image', required=True, help='Docker image to deploy')
    parser.add_argument('--docker-registry', help='Image path prefix for third-party images (e.g. postgres, nginx) via GitLab Dependency Proxy')
    parser.add_argument('--registry-username', help='Docker registry username')
    parser.add_argument('--registry-password', help='Docker registry password')
    parser.add_argument('--container-registry-server', help='Container registry server URL')
    parser.add_argument('--dependency-proxy-server', help='Dependency proxy server URL')
    parser.add_argument('--dependency-proxy-username', help='Dependency proxy username')
    parser.add_argument('--dependency-proxy-password', help='Dependency proxy password')
    parser.add_argument('--db-host', default='localhost', help='Database host')

    # Secret variables (from GitLab CI/CD variables) (can be context-specific)
    parser.add_argument('--postgres-user', help='PostgreSQL user')
    parser.add_argument('--postgres-password', help='PostgreSQL password')
    parser.add_argument('--postgres-db', help='PostgreSQL bootstrap DB')
    parser.add_argument('--nsft-db-name', help='Application database name')
    parser.add_argument('--secret-key', help='Flask SECRET_KEY')
    parser.add_argument('--telegram-bot-token', help='Telegram bot token')
    parser.add_argument('--telegram-chat-id', help='Telegram chat ID')
    parser.add_argument('--admin-user-username', help='Initial admin username')
    parser.add_argument('--admin-user-password', help='Initial admin password')
    parser.add_argument('--admin-user-first-name', help='Initial admin first name')
    parser.add_argument('--admin-user-last-name', help='Initial admin last name')
    parser.add_argument('--admin-user-email', help='Initial admin email')
    args = parser.parse_args()

    # Set the current directory to the script's directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Determine the target host based on the environment
    target_host = args.env

    # Always use docker_deploy.yml
    playbook = 'ansible/docker_deploy.yml'

    ensure_ansible_installed()

    # Build the Ansible command
    cmd = [
        'ansible-playbook',
        '-i', 'ansible/inventory.ini',
        playbook,
        '-e', f'deploy_action={args.action}',
        '-e', f'context={args.env}',
        '-e', f'target_host={target_host}',
        '-e', f'docker_image={args.docker_image}',
        '-e', f'docker_registry={args.docker_registry}',
        '-e', f'db_host={args.db_host}'
    ]

    if args.registry_username:
        cmd.extend(['-e', f'registry_username={args.registry_username}'])

    if args.registry_password:
        cmd.extend(['-e', f'registry_password={args.registry_password}'])

    if args.container_registry_server:
        cmd.extend(['-e', f'container_registry_server={args.container_registry_server}'])

    if args.dependency_proxy_server:
        cmd.extend(['-e', f'dependency_proxy_server={args.dependency_proxy_server}'])

    if args.dependency_proxy_username:
        cmd.extend(['-e', f'dependency_proxy_username={args.dependency_proxy_username}'])

    if args.dependency_proxy_password:
        cmd.extend(['-e', f'dependency_proxy_password={args.dependency_proxy_password}'])

    # Pass variables to Ansible (some are context-specific)
    context = args.env
    if args.postgres_user:
        cmd.extend(['-e', f'postgres_user={args.postgres_user}'])
    if args.postgres_password:
        cmd.extend(['-e', f'{context}_postgres_password={args.postgres_password}'])
    if args.postgres_db:
        cmd.extend(['-e', f'postgres_db={args.postgres_db}'])
    if args.nsft_db_name:
        cmd.extend(['-e', f'{context}_nsft_db_name={args.nsft_db_name}'])
    if args.secret_key:
        cmd.extend(['-e', f'{context}_secret_key={args.secret_key}'])
    if args.telegram_bot_token:
        cmd.extend(['-e', f'{context}_telegram_bot_token={args.telegram_bot_token}'])
    if args.telegram_chat_id:
        cmd.extend(['-e', f'{context}_telegram_chat_id={args.telegram_chat_id}'])
    if args.admin_user_username:
        cmd.extend(['-e', f'admin_user_username={args.admin_user_username}'])
    if args.admin_user_password:
        cmd.extend(['-e', f'{context}_admin_user_password={args.admin_user_password}'])
    if args.admin_user_first_name:
        cmd.extend(['-e', f'admin_user_first_name={args.admin_user_first_name}'])
    if args.admin_user_last_name:
        cmd.extend(['-e', f'admin_user_last_name={args.admin_user_last_name}'])
    if args.admin_user_email:
        cmd.extend(['-e', f'admin_user_email={args.admin_user_email}'])

    # Install Ansible collection
    try:
        subprocess.check_call(['ansible-galaxy', 'collection', 'install', '-r', 'ansible/requirements.yml'])
    except FileNotFoundError:
        print("ansible-galaxy command not found after bootstrap.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error installing Ansible collection: {e}", file=sys.stderr)
        sys.exit(1)
    # Run the Ansible command
    try:
        subprocess.check_call(cmd)
    except FileNotFoundError:
        print("ansible-playbook command not found after bootstrap.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Error running Ansible: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
