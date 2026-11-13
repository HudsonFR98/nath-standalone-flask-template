import logging
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from sqlalchemy import desc
from flask_babel import gettext as _

from nath_standalone_flask_template.lib import config
from nath_standalone_flask_template.lib.const import CONTEXT_VALIDATION
from nath_standalone_flask_template.lib.flask_util import (
    admin_required,
    admin_role_required,
    staff_required,
)
from nath_standalone_flask_template.lib.exc import DomainError
from nath_standalone_flask_template.models.task import TaskExecution, ScheduledTask
from nath_standalone_flask_template.models.user import User
from nath_standalone_flask_template.lib.task_scheduler import task_scheduler
from nath_standalone_flask_template.lib.database import DBSession
from nath_standalone_flask_template import dao

admin = Blueprint('admin', __name__, url_prefix='/admin')
log = logging.getLogger(__name__)





@admin.route('/tasks')
@login_required
@staff_required
def tasks():
    """Async tasks management page"""
    try:
        # Get active scheduled tasks
        active_tasks = ScheduledTask.query.filter_by(is_active=True).all()
        
        # Calculate statistics from entire database
        from sqlalchemy import func
        total_executions = TaskExecution.query.count()
        success_count = TaskExecution.query.filter_by(status='completed').count()
        failed_count = TaskExecution.query.filter_by(status='failed').count()
        success_rate = (success_count / total_executions * 100) if total_executions > 0 else 0
        
        return render_template('admin/tasks.html',
                              active_tasks=active_tasks,
                              total_executions=total_executions,
                              success_count=success_count,
                              failed_count=failed_count,
                              success_rate=round(success_rate, 1))
    
    except Exception as e:
        log.error(f"Error loading tasks page: {e}")
        flash(_('Error loading tasks data. Please check database connection.'), 'error')
        return render_template('admin/tasks.html',
                              active_tasks=[],
                              total_executions=0,
                              success_count=0,
                              failed_count=0,
                              success_rate=0)


@admin.route('/api/task/<task_name>/status')
@login_required
@staff_required
def task_status(task_name):
    """Get task status API endpoint"""
    try:
        job_status = task_scheduler.get_job_status(task_name)
        scheduled_task = ScheduledTask.get_task_by_name(task_name)
        
        next_run = job_status.get('next_run')
        next_run_str = None
        if next_run is not None and hasattr(next_run, 'isoformat'):
            try:
                next_run_str = next_run.isoformat()
            except (AttributeError, TypeError):
                next_run_str = None
        
        scheduled_task_data = None
        if scheduled_task:
            last_run_str = scheduled_task.last_run.isoformat() if scheduled_task.last_run else None
            scheduled_task_data = {
                'cron_expression': scheduled_task.cron_expression,
                'description': scheduled_task.description,
                'last_run': last_run_str
            }
        
        return jsonify({
            'task_name': task_name,
            'job_active': job_status.get('active', False),
            'next_run': next_run_str,
            'scheduled_task': scheduled_task_data
        })
    
    except Exception as e:
        log.error(f"Error getting task status for {task_name}: {e}")
        return jsonify({'error': str(e)}), 500





@admin.route('/api/executions')
@login_required
@staff_required
def executions():
    """Get task executions with filtering"""
    try:
        # Get query parameters
        task_name = request.args.get('task_name')
        status = request.args.get('status')
        limit = int(request.args.get('limit', 50))
        
        # Build query
        query = TaskExecution.query
        
        if task_name:
            query = query.filter(TaskExecution.task_name == task_name)
        
        if status:
            query = query.filter(TaskExecution.status == status)
        
        # Get executions
        executions = query.order_by(TaskExecution.created_at.desc()).limit(limit).all()
        
        # Convert to JSON-serializable format
        executions_data = []
        for execution in executions:
            executions_data.append({
                'id': execution.id,
                'task_name': execution.task_name,
                'task_id': execution.task_id,
                'status': execution.status,
                'started_at': execution.started_at.isoformat() if execution.started_at else None,
                'completed_at': execution.completed_at.isoformat() if execution.completed_at else None,
                'execution_time': execution.execution_time,
                'result': execution.result,
                'error_message': execution.error_message,
                'created_at': execution.created_at.isoformat() if execution.created_at else None
            })
        
        return jsonify({'executions': executions_data})
    
    except Exception as e:
        log.error(f"Error getting executions: {e}")
        return jsonify({'error': str(e)}), 500


@admin.route('/api/statistics')
@login_required
@staff_required
def statistics():
    """Get task execution statistics"""
    try:
        # Get date range from query parameters
        days = int(request.args.get('days', 7))
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get executions in date range
        executions = TaskExecution.query.filter(
            TaskExecution.created_at >= start_date
        ).all()
        
        # Calculate statistics
        total = len(executions)
        completed = len([e for e in executions if e.status == 'completed'])
        failed = len([e for e in executions if e.status == 'failed'])
        running = len([e for e in executions if e.status == 'running'])
        
        # Calculate average execution time
        completed_executions = [e for e in executions if e.status == 'completed' and e.execution_time]
        avg_execution_time = sum(e.execution_time for e in completed_executions) / len(completed_executions) if completed_executions else 0
        
        # Group by task name
        task_stats = {}
        for execution in executions:
            task_name = execution.task_name
            if task_name not in task_stats:
                task_stats[task_name] = {'total': 0, 'completed': 0, 'failed': 0, 'running': 0}
            
            task_stats[task_name]['total'] += 1
            if execution.status == 'completed':
                task_stats[task_name]['completed'] += 1
            elif execution.status == 'failed':
                task_stats[task_name]['failed'] += 1
            elif execution.status == 'running':
                task_stats[task_name]['running'] += 1
        
        return jsonify({
            'period_days': days,
            'total_executions': total,
            'completed': completed,
            'failed': failed,
            'running': running,
            'success_rate': (completed / total * 100) if total > 0 else 0,
            'avg_execution_time': round(avg_execution_time, 2),
            'task_statistics': task_stats
        })
    
    except Exception as e:
        log.error(f"Error getting statistics: {e}")
        return jsonify({'error': str(e)}), 500


@admin.route('/logs')
@login_required
@admin_role_required
def logs():
    """View application logs"""
    try:
        # Get log file path
        log_file = '/var/log/nath_standalone_flask_template/nath_standalone_flask_template.log'
        
        # Read last 1000 lines of log file
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                # Get last 1000 lines and strip newline characters
                log_lines = [line.rstrip('\n') for line in (lines[-1000:] if len(lines) > 1000 else lines)]
        except FileNotFoundError:
            log_lines = ["Log file not found"]
        except Exception as e:
            log_lines = [f"Error reading log file: {e}"]
        
        return render_template('admin/logs.html', log_lines=log_lines)
    
    except Exception as e:
        log.error(f"Error loading logs: {e}")
        flash(_('Error loading logs'), 'error')
        return render_template('admin/logs.html', log_lines=[])


@admin.route('/users')
@login_required
@staff_required
def users():
    """Users management page"""
    try:
        # Get all users
        users = User.query.all()
        
        available_roles = dao.list_roles()

        return render_template(
            'admin/users.html',
            users=users,
            available_roles=available_roles,
            validation_reviewer_guest_login=dao.is_validation_reviewer_guest_login_enabled(),
            show_validation_guest_setting=(config.CONTEXT == CONTEXT_VALIDATION),
        )

    except Exception as e:
        log.error(f"Error loading users page: {e}")
        flash(_('Error loading users data. Please check database connection.'), 'error')
        return render_template(
            'admin/users.html',
            users=[],
            available_roles=[],
            validation_reviewer_guest_login=False,
            show_validation_guest_setting=(config.CONTEXT == CONTEXT_VALIDATION),
        )


@admin.route('/settings/validation-reviewer-guest', methods=['POST'])
@login_required
@admin_required
def set_validation_reviewer_guest():
    if config.CONTEXT != CONTEXT_VALIDATION:
        flash(_('This setting only applies in the validation context.'), 'error')
        return redirect(url_for('admin.users'))
    enabled = request.form.get('enabled') == 'on'
    dao.set_validation_reviewer_guest_login(enabled)
    flash(
        _('Validation reviewer guest login enabled.')
        if enabled
        else _('Validation reviewer guest login disabled.'),
        'message',
    )
    return redirect(url_for('admin.users'))


@admin.route('/create_user', methods=['POST'])
@login_required
@admin_required
def create_user():
    """Create a new user"""
    try:
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        role_ids = request.form.getlist('roles')
        
        # Validate required fields
        if not username or not password:
            flash(_('Username and password are required.'), 'error')
            return redirect(url_for('admin.users'))
        
        # Check if username already exists
        if User.query.filter_by(ide=username).first():
            flash(_('Username already exists.'), 'error')
            return redirect(url_for('admin.users'))
        
        # Create new user
        new_user = User(
            ide=username,
            pwd=password,  # Will be hashed by the model validator
            first_name=first_name if first_name else None,
            last_name=last_name if last_name else None,
            email=email if email else None,
            active=True
        )
        
        # Add roles
        for role_id in role_ids:
            try:
                role = dao.get_role(int(role_id))
                if role:
                    new_user.add_role(role)
            except (ValueError, TypeError):
                log.warning(f"Invalid role ID: {role_id}")
        
        DBSession.add(new_user)
        DBSession.commit()
        
        flash(_('User created successfully.'), 'message')
        log.info(f"User '{username}' created by admin '{current_user.ide}'")
        
    except Exception as e:
        log.error(f"Error creating user: {e}")
        flash(_('Error creating user. Please try again.'), 'error')
        DBSession.rollback()
    
    return redirect(url_for('admin.users'))


@admin.route('/edit_user', methods=['POST'])
@login_required
@admin_required
def edit_user():
    """Edit an existing user"""
    try:
        user_id = request.form.get('user_id')
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        role_ids = request.form.getlist('roles')
        
        if not user_id:
            flash(_('User ID is required.'), 'error')
            return redirect(url_for('admin.users'))
        
        # Get user
        user = User.query.get(int(user_id))
        if not user:
            flash(_('User not found.'), 'error')
            return redirect(url_for('admin.users'))
        
        # Validate required fields
        if not username:
            flash(_('Username is required.'), 'error')
            return redirect(url_for('admin.users'))
        
        # Check if username already exists (excluding current user)
        existing_user = User.query.filter_by(ide=username).first()
        if existing_user and existing_user.id != user.id:
            flash(_('Username already exists.'), 'error')
            return redirect(url_for('admin.users'))
        
        # Update user fields
        user.ide = username
        if password:  # Only update password if provided
            user.pwd = password  # Will be hashed by the model validator
        user.first_name = first_name if first_name else None
        user.last_name = last_name if last_name else None
        user.email = email if email else None
        
        # Update roles
        user.roles.clear()  # Remove all existing roles
        for role_id in role_ids:
            try:
                role = dao.get_role(int(role_id))
                if role:
                    user.add_role(role)
            except (ValueError, TypeError):
                log.warning(f"Invalid role ID: {role_id}")
        
        DBSession.commit()
        
        flash(_('User updated successfully.'), 'message')
        log.info(f"User '{username}' updated by admin '{current_user.ide}'")
        
    except Exception as e:
        log.error(f"Error updating user: {e}")
        flash(_('Error updating user. Please try again.'), 'error')
        DBSession.rollback()
    
    return redirect(url_for('admin.users'))


@admin.route('/api/user/<int:user_id>')
@login_required
@admin_required
def get_user(user_id):
    """Get user data for editing"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'id': user.id,
            'ide': user.ide,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'active': user.active,
            'roles': [role.id for role in user.roles],
            'has_api_token': user.has_api_token(),
            'api_token_prefix': user.api_token_prefix,
            'api_token_created_at': (
                user.api_token_created_at.isoformat()
                if user.api_token_created_at else None
            ),
        })
    
    except Exception as e:
        log.error(f"Error getting user data: {e}")
        return jsonify({'error': str(e)}), 500


@admin.route('/api/user/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    """Toggle user active status"""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        
        # Don't allow deactivating yourself
        if user.id == current_user.id:
            return jsonify({'success': False, 'message': 'Cannot deactivate your own account'}), 400
        
        user.active = not user.active
        DBSession.commit()
        
        status = 'activated' if user.active else 'deactivated'
        log.info(f"User '{user.ide}' {status} by admin '{current_user.ide}'")
        
        return jsonify({'success': True, 'message': f'User {status} successfully'})
    
    except Exception as e:
        log.error(f"Error toggling user status: {e}")
        DBSession.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


def _api_token_payload(user, token=None):
    payload = {
        'success': True,
        'user_id': user.id,
        'username': user.ide,
        'has_api_token': user.has_api_token(),
        'prefix': user.api_token_prefix,
        'created_at': (
            user.api_token_created_at.isoformat()
            if user.api_token_created_at else None
        ),
    }
    if token is not None:
        payload['token'] = token
    return payload


@admin.route('/api/user/<int:user_id>/token', methods=['POST'])
@login_required
@admin_required
def generate_user_api_token(user_id):
    try:
        result = dao.generate_api_token(user_id)
        log.info(
            "API token generated for user '%s' by admin '%s'",
            result['user'].ide,
            current_user.ide,
        )
        return jsonify(_api_token_payload(result['user'], token=result['token']))
    except DomainError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        log.error(f"Error generating API token: {e}")
        DBSession.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@admin.route('/api/user/<int:user_id>/token/revoke', methods=['POST'])
@login_required
@admin_required
def revoke_user_api_token(user_id):
    try:
        user = dao.revoke_api_token(user_id)
        log.info(
            "API token revoked for user '%s' by admin '%s'",
            user.ide,
            current_user.ide,
        )
        return jsonify(_api_token_payload(user))
    except DomainError as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        log.error(f"Error revoking API token: {e}")
        DBSession.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500


@admin.route('/roles')
@login_required
@staff_required
def roles():
    """Roles management page"""
    try:
        return render_template(
            'admin/roles.html',
            roles=dao.list_roles(),
            available_permissions=dao.list_permissions(),
        )
    except Exception as e:
        log.error(f"Error loading roles page: {e}")
        flash(_('Error loading roles data. Please check database connection.'), 'error')
        return render_template('admin/roles.html', roles=[], available_permissions=[])


@admin.route('/roles/create', methods=['POST'])
@login_required
@admin_required
def create_role():
    try:
        dao.create_role(
            name=request.form.get('name', ''),
            description=request.form.get('description', ''),
            permission_ids=request.form.getlist('permissions'),
        )
        flash(_('Role created successfully.'), 'message')
        log.info("Role created by admin '%s'", current_user.ide)
    except DomainError as e:
        flash(str(e), 'error')
    except Exception as e:
        log.error(f"Error creating role: {e}")
        flash(_('Error creating role. Please try again.'), 'error')
        DBSession.rollback()
    return redirect(url_for('admin.roles'))


@admin.route('/roles/edit', methods=['POST'])
@login_required
@admin_required
def edit_role():
    try:
        dao.update_role(
            pk=int(request.form.get('role_id')),
            name=request.form.get('name', ''),
            description=request.form.get('description', ''),
            permission_ids=request.form.getlist('permissions'),
        )
        flash(_('Role updated successfully.'), 'message')
        log.info("Role updated by admin '%s'", current_user.ide)
    except (TypeError, ValueError):
        flash(_('Role ID is required.'), 'error')
    except DomainError as e:
        flash(str(e), 'error')
    except Exception as e:
        log.error(f"Error updating role: {e}")
        flash(_('Error updating role. Please try again.'), 'error')
        DBSession.rollback()
    return redirect(url_for('admin.roles'))


@admin.route('/roles/delete', methods=['POST'])
@login_required
@admin_required
def delete_role():
    try:
        dao.delete_role(int(request.form.get('role_id')))
        flash(_('Role deleted successfully.'), 'message')
        log.info("Role deleted by admin '%s'", current_user.ide)
    except (TypeError, ValueError):
        flash(_('Role ID is required.'), 'error')
    except DomainError as e:
        flash(str(e), 'error')
    except Exception as e:
        log.error(f"Error deleting role: {e}")
        flash(_('Error deleting role. Please try again.'), 'error')
        DBSession.rollback()
    return redirect(url_for('admin.roles'))


@admin.route('/api/role/<int:role_id>')
@login_required
@admin_required
def get_role(role_id):
    try:
        role = dao.get_role(role_id)
        if role is None:
            return jsonify({'error': 'Role not found'}), 404
        return jsonify({
            'id': role.id,
            'name': role.name,
            'description': role.description,
            'is_admin': role.is_admin_role(),
            'permissions': [permission.id for permission in role.granted_permissions],
        })
    except Exception as e:
        log.error(f"Error getting role data: {e}")
        return jsonify({'error': str(e)}), 500


@admin.route('/permissions')
@login_required
@staff_required
def permissions():
    """Permissions management page"""
    try:
        return render_template(
            'admin/permissions.html',
            permissions=dao.list_permissions(),
        )
    except Exception as e:
        log.error(f"Error loading permissions page: {e}")
        flash(_('Error loading permissions data. Please check database connection.'), 'error')
        return render_template('admin/permissions.html', permissions=[])


@admin.route('/permissions/create', methods=['POST'])
@login_required
@admin_required
def create_permission():
    try:
        dao.create_permission(
            name=request.form.get('name', ''),
            description=request.form.get('description', ''),
        )
        flash(_('Permission created successfully.'), 'message')
        log.info("Permission created by admin '%s'", current_user.ide)
    except DomainError as e:
        flash(str(e), 'error')
    except Exception as e:
        log.error(f"Error creating permission: {e}")
        flash(_('Error creating permission. Please try again.'), 'error')
        DBSession.rollback()
    return redirect(url_for('admin.permissions'))


@admin.route('/permissions/edit', methods=['POST'])
@login_required
@admin_required
def edit_permission():
    try:
        dao.update_permission(
            pk=int(request.form.get('permission_id')),
            description=request.form.get('description', ''),
        )
        flash(_('Permission updated successfully.'), 'message')
        log.info("Permission updated by admin '%s'", current_user.ide)
    except (TypeError, ValueError):
        flash(_('Permission ID is required.'), 'error')
    except DomainError as e:
        flash(str(e), 'error')
    except Exception as e:
        log.error(f"Error updating permission: {e}")
        flash(_('Error updating permission. Please try again.'), 'error')
        DBSession.rollback()
    return redirect(url_for('admin.permissions'))


@admin.route('/permissions/delete', methods=['POST'])
@login_required
@admin_required
def delete_permission():
    try:
        dao.delete_permission(int(request.form.get('permission_id')))
        flash(_('Permission deleted successfully.'), 'message')
        log.info("Permission deleted by admin '%s'", current_user.ide)
    except (TypeError, ValueError):
        flash(_('Permission ID is required.'), 'error')
    except DomainError as e:
        flash(str(e), 'error')
    except Exception as e:
        log.error(f"Error deleting permission: {e}")
        flash(_('Error deleting permission. Please try again.'), 'error')
        DBSession.rollback()
    return redirect(url_for('admin.permissions')) 